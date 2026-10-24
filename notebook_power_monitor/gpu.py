"""NVIDIA GPU telemetry via NVML.

NVML is the same source NVIDIA App uses for power/temperature/utilisation.
Queries run on their own daemon thread.  If the dGPU is powered down, the
driver returns an error, zero, or stops answering; in all three cases the
published sample ages out / is marked unavailable instead of reusing an old
wattage.
"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from dataclasses import replace
from pathlib import Path

from .models import GpuNvmlReading, SourceStatus
from .util import LOG, fmt_age

NVML_SUCCESS = 0
NVML_ERROR_UNINITIALIZED = 1
NVML_ERROR_INVALID_ARGUMENT = 2
NVML_ERROR_NOT_SUPPORTED = 3
NVML_ERROR_NO_PERMISSION = 4
NVML_ERROR_NOT_FOUND = 6
NVML_ERROR_DRIVER_NOT_LOADED = 9
NVML_ERROR_TIMEOUT = 10
NVML_ERROR_GPU_IS_LOST = 14
NVML_ERROR_RESET_REQUIRED = 15

NVML_TEMPERATURE_GPU = 0


class nvmlUtilization_t(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


def _error_text(code: int) -> str:
    return {
        0: "成功",
        1: "NVML 未初始化",
        2: "参数错误",
        3: "设备不支持该指标",
        4: "没有权限",
        6: "未找到 NVIDIA GPU",
        9: "NVIDIA 驱动未加载",
        10: "NVML 查询超时",
        14: "GPU 已丢失（可能已断电/复位）",
        15: "GPU 需要复位",
    }.get(code, f"NVML 错误 {code}")


class NvmlReader:
    def __init__(self) -> None:
        self._lib = None
        self._handle = None
        self._name = "NVIDIA GPU"
        self._initialized = False
        self._last_init_attempt = 0.0
        self._init_error = ""
        self._device_count = 0

    def _load(self) -> bool:
        if self._lib is not None:
            return True
        candidates = [
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "nvml.dll",
            Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvml.dll"),
            Path(r"C:\Program Files\NVIDIA Corporation\NVIDIA App\nvml.dll"),
        ]
        for path in candidates:
            if not path.is_file():
                continue
            try:
                if path.parent.name.lower() != "system32":
                    try:
                        os.add_dll_directory(str(path.parent))
                    except Exception:
                        pass
                self._lib = ctypes.WinDLL(str(path))
                return True
            except OSError:
                continue
        try:
            self._lib = ctypes.WinDLL("nvml.dll")
            return True
        except OSError as exc:
            self._init_error = f"无法加载 nvml.dll：{exc}"
            return False

    def _bind(self) -> None:
        lib = self._lib
        assert lib is not None
        try:
            lib.nvmlInit_v2.restype = ctypes.c_int
            lib.nvmlInit_v2.argtypes = []
            self._init_fn = lib.nvmlInit_v2
        except AttributeError:
            lib.nvmlInit.restype = ctypes.c_int
            lib.nvmlInit.argtypes = []
            self._init_fn = lib.nvmlInit
        try:
            lib.nvmlDeviceGetCount_v2.restype = ctypes.c_int
            lib.nvmlDeviceGetCount_v2.argtypes = [ctypes.POINTER(ctypes.c_uint)]
            self._count_fn = lib.nvmlDeviceGetCount_v2
        except AttributeError:
            lib.nvmlDeviceGetCount.restype = ctypes.c_int
            lib.nvmlDeviceGetCount.argtypes = [ctypes.POINTER(ctypes.c_uint)]
            self._count_fn = lib.nvmlDeviceGetCount
        try:
            lib.nvmlDeviceGetHandleByIndex_v2.restype = ctypes.c_int
            lib.nvmlDeviceGetHandleByIndex_v2.argtypes = [
                ctypes.c_uint,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            self._handle_fn = lib.nvmlDeviceGetHandleByIndex_v2
        except AttributeError:
            lib.nvmlDeviceGetHandleByIndex.restype = ctypes.c_int
            lib.nvmlDeviceGetHandleByIndex.argtypes = [
                ctypes.c_uint,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            self._handle_fn = lib.nvmlDeviceGetHandleByIndex
        lib.nvmlDeviceGetName.restype = ctypes.c_int
        lib.nvmlDeviceGetName.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        lib.nvmlDeviceGetPowerUsage.restype = ctypes.c_int
        lib.nvmlDeviceGetPowerUsage.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint),
        ]
        lib.nvmlDeviceGetTemperature.restype = ctypes.c_int
        lib.nvmlDeviceGetTemperature.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_uint),
        ]
        lib.nvmlDeviceGetUtilizationRates.restype = ctypes.c_int
        lib.nvmlDeviceGetUtilizationRates.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(nvmlUtilization_t),
        ]
        lib.nvmlShutdown.restype = ctypes.c_int
        lib.nvmlShutdown.argtypes = []

    def _init(self) -> bool:
        now = time.time()
        if self._initialized and self._handle:
            return True
        if now - self._last_init_attempt < 4.0:
            return False
        self._last_init_attempt = now
        if not self._load():
            return False
        if not getattr(self, "_init_fn", None):
            self._bind()
        rc = int(self._init_fn())
        if rc != NVML_SUCCESS:
            self._init_error = _error_text(rc)
            self._initialized = False
            self._handle = None
            return False
        try:
            count = ctypes.c_uint(0)
            rc = int(self._count_fn(ctypes.byref(count)))
            if rc != NVML_SUCCESS:
                self._init_error = _error_text(rc)
                self._shutdown_lib()
                return False
            self._device_count = int(count.value)
            if self._device_count <= 0:
                self._init_error = "NVML 未发现 NVIDIA GPU"
                self._shutdown_lib()
                return False
            chosen = None
            chosen_name = "NVIDIA GPU"
            for index in range(self._device_count):
                handle = ctypes.c_void_p()
                rc = int(self._handle_fn(index, ctypes.byref(handle)))
                if rc != NVML_SUCCESS or not handle:
                    continue
                name = self._device_name(handle)
                if chosen is None or "nvidia" in name.lower():
                    chosen = handle
                    chosen_name = name
                    if "nvidia" in name.lower() or "geforce" in name.lower():
                        break
            if chosen is None:
                self._init_error = "无法获取 NVIDIA GPU 句柄"
                self._shutdown_lib()
                return False
            self._handle = chosen
            self._name = chosen_name
            self._initialized = True
            self._init_error = ""
            LOG.info("NVML connected: %s", chosen_name)
            return True
        except Exception as exc:
            self._init_error = f"NVML 初始化失败：{exc}"
            LOG.exception("NVML init failed")
            self._shutdown_lib()
            return False

    def _device_name(self, handle) -> str:
        buf = ctypes.create_string_buffer(128)
        rc = self._lib.nvmlDeviceGetName(handle, buf, 128)  # type: ignore[union-attr]
        if rc == NVML_SUCCESS:
            try:
                return buf.value.decode("utf-8", errors="replace")
            except Exception:
                return "NVIDIA GPU"
        return "NVIDIA GPU"

    def _shutdown_lib(self) -> None:
        if self._initialized and self._lib is not None:
            try:
                self._lib.nvmlShutdown()
            except Exception:
                pass
        self._initialized = False
        self._handle = None

    def close(self) -> None:
        self._shutdown_lib()

    def read(self) -> GpuNvmlReading:
        now = time.time()
        if not self._init():
            return GpuNvmlReading(
                available=False,
                name=self._name,
                power_w=None,
                temp_c=None,
                util_pct=None,
                mem_util_pct=None,
                error=self._init_error or "NVML 不可用",
                timestamp=now,
            )
        power = ctypes.c_uint(0)
        rc_power = int(
            self._lib.nvmlDeviceGetPowerUsage(self._handle, ctypes.byref(power))  # type: ignore[union-attr]
        )
        temp = ctypes.c_uint(0)
        rc_temp = int(
            self._lib.nvmlDeviceGetTemperature(  # type: ignore[union-attr]
                self._handle, NVML_TEMPERATURE_GPU, ctypes.byref(temp)
            )
        )
        util = nvmlUtilization_t()
        rc_util = int(
            self._lib.nvmlDeviceGetUtilizationRates(  # type: ignore[union-attr]
                self._handle, ctypes.byref(util)
            )
        )

        if rc_power == NVML_ERROR_GPU_IS_LOST or rc_power == NVML_ERROR_UNINITIALIZED:
            self._init_error = _error_text(rc_power)
            self._shutdown_lib()
            return GpuNvmlReading(
                available=False,
                name=self._name,
                error=self._init_error,
                timestamp=time.time(),
            )

        if rc_power == NVML_SUCCESS:
            watts = power.value / 1000.0
            if watts > 0.05:
                return GpuNvmlReading(
                    available=True,
                    name=self._name,
                    power_w=watts,
                    temp_c=float(temp.value) if rc_temp == NVML_SUCCESS else None,
                    util_pct=float(util.gpu) if rc_util == NVML_SUCCESS else None,
                    mem_util_pct=float(util.memory) if rc_util == NVML_SUCCESS else None,
                    error="",
                    timestamp=time.time(),
                )
            return GpuNvmlReading(
                available=False,
                name=self._name,
                power_w=None,
                temp_c=float(temp.value) if rc_temp == NVML_SUCCESS else None,
                util_pct=float(util.gpu) if rc_util == NVML_SUCCESS else None,
                mem_util_pct=None,
                error="GPU 功耗读数为 0（独显可能已休眠）",
                timestamp=time.time(),
            )
        if rc_power == NVML_ERROR_NOT_SUPPORTED:
            self._init_error = "此 NVIDIA GPU/驱动不支持功耗传感器"
        else:
            self._init_error = _error_text(rc_power)
        return GpuNvmlReading(
            available=False,
            name=self._name,
            power_w=None,
            temp_c=float(temp.value) if rc_temp == NVML_SUCCESS else None,
            util_pct=float(util.gpu) if rc_util == NVML_SUCCESS else None,
            mem_util_pct=None,
            error=self._init_error,
            timestamp=time.time(),
        )

    def status(self) -> SourceStatus:
        if self._initialized and self._handle:
            return SourceStatus(
                "nvml",
                "NVIDIA",
                "ok",
                self._name,
                f"NVML 实时传感器 · {self._device_count} 个设备",
                time.time(),
            )
        return SourceStatus(
            "nvml",
            "NVIDIA",
            "off" if self._init_error else "warn",
            "不可用" if self._init_error else "正在探测",
            self._init_error or "尚未初始化 NVML",
            time.time(),
        )


class GpuSampler:
    """Continuously polls NVML and publishes only live samples."""

    def __init__(self, interval: float = 1.0) -> None:
        self._interval = interval
        self._reader = NvmlReader()
        self._lock = threading.Lock()
        self._state = GpuNvmlReading(
            available=False,
            name="NVIDIA GPU",
            error="正在探测 NVIDIA GPU",
            timestamp=0.0,
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_status: SourceStatus = self._reader.status()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="GPU-NVML", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                reading = self._reader.read()
            except Exception as exc:
                LOG.exception("NVML read failed")
                reading = GpuNvmlReading(
                    available=False,
                    name=self._state.name,
                    error=f"NVML 读取异常：{exc}",
                    timestamp=time.time(),
                )
            with self._lock:
                self._state = reading
                self._last_status = self._reader.status()
            self._stop.wait(self._interval)

    def latest(self) -> tuple[GpuNvmlReading, float]:
        with self._lock:
            state = replace(self._state)
        return state, max(0.0, time.time() - state.timestamp) if state.timestamp else 9999.0

    def status(self) -> SourceStatus:
        with self._lock:
            status = self._last_status
            state = replace(self._state)
        if state.timestamp and not state.available:
            status.detail = state.error or status.detail
            if status.state == "ok":
                status.state = "warn"
        return status

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.5)
        self._reader.close()

    @property
    def display_name(self) -> str:
        with self._lock:
            return self._state.name or "NVIDIA GPU"


def combined_gpu_age_text(age: float) -> str:
    return fmt_age(age)
