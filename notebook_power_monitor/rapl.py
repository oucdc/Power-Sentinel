"""Native Windows energy counters (PDH).

Modern Windows exposes the CPU package energy through the ``Energy Meter``
counter set, backed by Intel RAPL / AMD SMU hardware counters.  Some machines
also publish a whole-machine ``Power Meter`` counter (EMI).  These are real
firmware counters, not estimates.

The counters report milliwatts in this API's CookedValue, so values are divided
by 1000.  A counter that remains at 0 is treated as unavailable, never as 0 W.
"""

from __future__ import annotations

import ctypes
import math
import time
from ctypes import wintypes
from dataclasses import dataclass

from .models import SourceStatus
from .util import LOG

PDH_FMT_DOUBLE = 0x00000200
PDH_CSTATUS_VALID_DATA = 0x00000000
PDH_CSTATUS_NEW_DATA = 0x00000001
ERROR_SUCCESS = 0

PDH_HQUERY = ctypes.c_void_p
PDH_HCOUNTER = ctypes.c_void_p


class _PDH_FMT_COUNTERVALUE_UNION(ctypes.Union):
    _fields_ = [
        ("longValue", ctypes.c_long),
        ("doubleValue", ctypes.c_double),
        ("largeValue", ctypes.c_longlong),
        ("AnsiStringValue", ctypes.c_char_p),
        ("WideStringValue", ctypes.c_wchar_p),
    ]


class PDH_FMT_COUNTERVALUE(ctypes.Structure):
    _fields_ = [
        ("CStatus", wintypes.DWORD),
        ("u", _PDH_FMT_COUNTERVALUE_UNION),
    ]


pdh = ctypes.WinDLL("pdh", use_last_error=True)
pdh.PdhOpenQueryW.restype = ctypes.c_long
pdh.PdhOpenQueryW.argtypes = [
    wintypes.LPCWSTR,
    ctypes.c_size_t,
    ctypes.POINTER(PDH_HQUERY),
]
pdh.PdhAddEnglishCounterW.restype = ctypes.c_long
pdh.PdhAddEnglishCounterW.argtypes = [
    PDH_HQUERY,
    wintypes.LPCWSTR,
    ctypes.c_size_t,
    ctypes.POINTER(PDH_HCOUNTER),
]
pdh.PdhAddCounterW.restype = ctypes.c_long
pdh.PdhAddCounterW.argtypes = [
    PDH_HQUERY,
    wintypes.LPCWSTR,
    ctypes.c_size_t,
    ctypes.POINTER(PDH_HCOUNTER),
]
pdh.PdhCollectQueryData.restype = ctypes.c_long
pdh.PdhCollectQueryData.argtypes = [PDH_HQUERY]
pdh.PdhGetFormattedCounterValue.restype = ctypes.c_long
pdh.PdhGetFormattedCounterValue.argtypes = [
    PDH_HCOUNTER,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(PDH_FMT_COUNTERVALUE),
]
pdh.PdhCloseQuery.restype = ctypes.c_long
pdh.PdhCloseQuery.argtypes = [PDH_HQUERY]


def _status_text(code: int) -> str:
    known = {
        0: "成功",
        0xC0000BB8: "对象不存在",
        0xC0000BB9: "计数器不存在",
        0xC0000BC0: "计数器路径无效",
        0xC0000BC6: "数据不足",
        0xC0000BC7: "实例不存在",
        0xC0000BDB: "访问被拒绝",
        0xC0000BCA: "方法无效",
    }
    return known.get(code & 0xFFFFFFFF, f"PDH 状态 0x{code & 0xFFFFFFFF:08X}")


@dataclass
class PdhReading:
    value_w: float | None
    status: SourceStatus


class PdhPowerGroup:
    """One PDH query holding one or more power counters."""

    def __init__(
        self,
        paths: list[str],
        label: str,
        mode: str = "sum",
        scale: float = 0.001,
        valid_max_w: float = 600.0,
    ) -> None:
        self.paths = paths
        self.label = label
        self.mode = mode  # sum | max
        self.scale = scale
        self.valid_max_w = valid_max_w
        self.query: int | None = None
        self.counters: list[int] = []
        self.added_paths: list[str] = []
        self.error = ""
        self.last_value: float | None = None
        self.last_status = "尚未初始化"
        self._primed = False
        self._last_read = 0.0
        self._closed = False

    def _open(self) -> bool:
        if self.query:
            return True
        query = PDH_HQUERY()
        rc = pdh.PdhOpenQueryW(None, 0, ctypes.byref(query))
        if rc != ERROR_SUCCESS:
            self.error = f"PdhOpenQuery 失败：{_status_text(rc)}"
            return False
        self.query = query
        for path in self.paths:
            counter = PDH_HCOUNTER()
            rc = pdh.PdhAddEnglishCounterW(query, path, 0, ctypes.byref(counter))
            if rc != ERROR_SUCCESS:
                counter = PDH_HCOUNTER()
                rc = pdh.PdhAddCounterW(query, path, 0, ctypes.byref(counter))
            if rc == ERROR_SUCCESS and counter:
                self.counters.append(counter)
                self.added_paths.append(path)
            else:
                LOG.info("PDH counter unavailable: %s (%s)", path, _status_text(rc))
        if not self.counters:
            self.error = "Windows 未提供对应的能量计数器"
            self._close_query()
            return False
        rc = pdh.PdhCollectQueryData(query)
        if rc != ERROR_SUCCESS:
            self.error = f"首次采集失败：{_status_text(rc)}"
            self._close_query()
            return False
        self._primed = True
        self.error = ""
        return True

    def _close_query(self) -> None:
        if self.query:
            try:
                pdh.PdhCloseQuery(self.query)
            except Exception:
                pass
        self.query = None
        self.counters = []
        self.added_paths = []
        self._primed = False

    def _collect_value(self) -> float | None:
        if not self.query:
            return None
        rc = pdh.PdhCollectQueryData(self.query)
        if rc != ERROR_SUCCESS:
            self.error = f"采集失败：{_status_text(rc)}"
            return None
        values: list[float] = []
        for counter in self.counters:
            val = PDH_FMT_COUNTERVALUE()
            ctype = wintypes.DWORD(0)
            rc = pdh.PdhGetFormattedCounterValue(
                counter,
                PDH_FMT_DOUBLE,
                ctypes.byref(ctype),
                ctypes.byref(val),
            )
            if rc != ERROR_SUCCESS:
                continue
            if val.CStatus not in (PDH_CSTATUS_VALID_DATA, PDH_CSTATUS_NEW_DATA):
                continue
            try:
                raw = float(val.u.doubleValue)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(raw):
                continue
            watts = raw * self.scale
            if 0.0 < watts <= self.valid_max_w:
                values.append(watts)
        if not values:
            return None
        if self.mode == "max":
            return max(values)
        return sum(values)

    def read(self) -> float | None:
        if self._closed:
            return None
        if not self.query and not self._open():
            self.last_value = None
            return None
        # The first value after opening has no elapsed interval.  The next
        # collector poll (~1 s later) is valid.
        value = self._collect_value()
        self._last_read = time.time()
        if value is not None:
            self.last_value = value
            self.last_status = "ok"
            return value
        self.last_value = None
        self.last_status = "无有效读数"
        return None

    def status(self) -> SourceStatus:
        if self.query:
            if self.last_value is not None:
                return SourceStatus(
                    "rapl" if "RAPL" in self.label else "power_meter",
                    self.label,
                    "ok",
                    f"{self.last_value:.1f} W",
                    " · ".join(self.added_paths),
                    self._last_read,
                    extra={"value_w": self.last_value, "paths": self.added_paths},
                )
            return SourceStatus(
                "rapl" if "RAPL" in self.label else "power_meter",
                self.label,
                "warn",
                "计数器无有效读数",
                self.error or self.last_status,
                self._last_read,
                extra={"paths": self.added_paths},
            )
        return SourceStatus(
            "rapl" if "RAPL" in self.label else "power_meter",
            self.label,
            "off",
            "不可用",
            self.error or "Windows 未提供此能量计数器",
            self._last_read,
        )

    def close(self) -> None:
        self._closed = True
        self._close_query()


class RaplReader(PdhPowerGroup):
    def __init__(self) -> None:
        super().__init__(
            [
                r"\Energy Meter(RAPL_Package0_PKG)\Power",
            ],
            label="RAPL CPU",
            mode="sum",
            scale=0.001,
            valid_max_w=500.0,
        )


class PowerMeterReader(PdhPowerGroup):
    def __init__(self) -> None:
        super().__init__(
            [
                r"\Power Meter(_Total)\Power",
                r"\Power Meter(Power Meter (0))\Power",
            ],
            label="Windows Power Meter",
            mode="max",
            scale=0.001,
            valid_max_w=1000.0,
        )
