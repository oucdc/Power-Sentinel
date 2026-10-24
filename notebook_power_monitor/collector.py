"""Collector that merges the native Windows sources into immutable snapshots.

HWiNFO integration has been removed.  CPU power comes from Windows RAPL, GPU
power from NVIDIA NVML, battery data from WMI/ACPI, and total power only from
Windows Power Meter or measured battery discharge.  There is no CPU+GPU sum
fallback.
"""

from __future__ import annotations

import collections
import platform
import statistics
import threading
import time
from dataclasses import replace

from .battery import BatteryRaw, BatteryReader, make_battery_info
from .gpu import GpuSampler
from .models import (
    BatteryInfo,
    CpuInfo,
    GpuInfo,
    Snapshot,
    SourceStatus,
)
from .processes import ProcessSampler
from .rapl import PowerMeterReader, RaplReader
from .util import LOG


def windows_cpu_name() -> str:
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        )
        value = winreg.QueryValueEx(key, "ProcessorNameString")[0]
        winreg.CloseKey(key)
        text = " ".join(str(value).split())
        text = text.replace("(R)", "").replace("(TM)", "")
        for prefix in ("Intel ", "AMD "):
            if text.startswith(prefix):
                text = text[len(prefix) :]
        return text.strip() or platform.processor() or "CPU"
    except Exception:
        return platform.processor() or "CPU"


class MonitoringEngine:
    def __init__(self, interval: float = 1.0) -> None:
        self.interval = max(0.5, min(5.0, interval))
        self.battery = BatteryReader()
        self.gpu = GpuSampler(interval=1.0)
        self.processes = ProcessSampler()
        self.rapl = RaplReader()
        self.power_meter = PowerMeterReader()
        self.cpu_name = windows_cpu_name()

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seq = 0
        self._latest = Snapshot(timestamp=time.time())
        self._battery_raw: BatteryRaw | None = None
        self._discharge_history: collections.deque[tuple[float, float]] = collections.deque()
        self._charge_history: collections.deque[tuple[float, float]] = collections.deque()
        self._last_direction = ""
        self._last_logged_sources = ""

    # -- lifecycle -----------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        LOG.info("Starting native collector (interval=%.2fs)", self.interval)
        self.gpu.start()
        self._thread = threading.Thread(target=self._run, name="SensorCollector", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                snap = self._build_snapshot()
            except Exception as exc:
                LOG.exception("Collector iteration failed")
                self._seq += 1
                now = time.time()
                error_status = SourceStatus(
                    "collector",
                    "采集器",
                    "error",
                    "采集异常",
                    f"{type(exc).__name__}: {exc}",
                    now,
                )
                snap = replace(
                    self._latest,
                    seq=self._seq,
                    timestamp=now,
                    total_w=None,
                    total_source="",
                    total_reason=f"采集异常：{type(exc).__name__}: {exc}",
                    cpu=replace(
                        self._latest.cpu,
                        power_w=None,
                        util_pct=None,
                        power_reason=f"采集异常：{exc}",
                    ),
                    gpu=replace(
                        self._latest.gpu,
                        power_w=None,
                        temp_c=None,
                        util_pct=None,
                        reason=f"采集异常：{exc}",
                    ),
                    battery_source=error_status,
                    background_source=error_status,
                    rapl=error_status,
                )
            with self._lock:
                self._latest = snap
            elapsed = time.monotonic() - started
            self._stop.wait(max(0.15, self.interval - elapsed))

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.gpu.stop()
        self.battery.close()
        self.rapl.close()
        self.power_meter.close()

    def latest(self) -> Snapshot:
        with self._lock:
            return self._latest

    # -- helpers -------------------------------------------------------
    def _runtime_estimate(self, raw: BatteryRaw) -> tuple[float | None, float | None]:
        now = time.time()
        if raw.power_w is not None and raw.direction in ("discharging", "charging"):
            if raw.direction != self._last_direction:
                self._discharge_history.clear()
                self._charge_history.clear()
                self._last_direction = raw.direction
            target = (
                self._discharge_history if raw.direction == "discharging" else self._charge_history
            )
            if not target or now - target[-1][0] >= 0.45 or abs(target[-1][1] - raw.power_w) > 0.01:
                target.append((now, raw.power_w))
            while target and now - target[0][0] > 20.0:
                target.popleft()
        else:
            if raw.direction != self._last_direction:
                self._discharge_history.clear()
                self._charge_history.clear()
                self._last_direction = raw.direction

        runtime: float | None = None
        to_full: float | None = None
        if raw.direction == "discharging" and raw.remaining_wh and self._discharge_history:
            rates = [w for _, w in self._discharge_history if w > 0.05]
            if rates:
                effective = statistics.median(rates)
                if effective > 0.05:
                    runtime = raw.remaining_wh / effective * 3600.0
        if (
            raw.direction == "charging"
            and raw.remaining_wh is not None
            and raw.full_wh
            and self._charge_history
        ):
            rates = [w for _, w in self._charge_history if w > 0.05]
            if rates:
                effective = statistics.median(rates)
                missing = max(0.0, raw.full_wh - raw.remaining_wh)
                if effective > 0.05 and missing > 0.05:
                    to_full = missing / effective * 3600.0
        return runtime, to_full

    def _cpu_from_rapl(
        self, rapl_w: float | None, rapl_status: SourceStatus, active_pct: float | None
    ) -> CpuInfo:
        if rapl_w is not None:
            return CpuInfo(
                name=self.cpu_name,
                power_w=rapl_w,
                temp_c=None,
                util_pct=active_pct,
                power_source="Windows RAPL · CPU Package",
                power_reason="",
                power_detail="PDH Energy Meter RAPL_Package0_PKG · 硬件能量计数器",
            )
        if rapl_status.state == "warn":
            reason = "RAPL 计数器暂无有效读数"
        else:
            reason = rapl_status.detail or "Windows RAPL 不可用"
        return CpuInfo(
            name=self.cpu_name,
            power_w=None,
            temp_c=None,
            util_pct=active_pct,
            power_source="",
            power_reason=reason,
            power_detail="",
        )

    def _gpu_from_nvml(
        self,
        nvml_state,
        nvml_age: float,
        nvml_status: SourceStatus,
    ) -> GpuInfo:
        name = nvml_state.name or "NVIDIA GPU"
        if nvml_age > 3.5:
            return GpuInfo(
                name=name,
                power_w=None,
                source="NVIDIA NVML",
                reason="NVML 超过 3.5 秒无响应，GPU 数据已失效",
                nvml_ok=False,
            )
        if not nvml_state.available or nvml_state.power_w is None:
            reason = nvml_state.error or nvml_status.detail or "NVIDIA GPU 不可用"
            lower = reason.lower()
            if "0（" in reason or "休眠" in reason or "lost" in lower or "丢失" in reason:
                reason = "独显已休眠 / 已断电，GPU 数据不可用"
            return GpuInfo(
                name=name,
                power_w=None,
                temp_c=None,
                util_pct=None,
                source="NVIDIA NVML",
                reason=reason,
                nvml_ok=False,
            )
        nvml_w = float(nvml_state.power_w)
        return GpuInfo(
            name=name,
            power_w=nvml_w,
            temp_c=nvml_state.temp_c,
            util_pct=nvml_state.util_pct,
            mem_util_pct=nvml_state.mem_util_pct,
            source="NVIDIA NVML",
            reason="",
            nvml_ok=True,
            power_detail=f"NVML 实测 {nvml_w:.2f} W",
        )

    def _build_snapshot(self) -> Snapshot:
        self._seq += 1
        now = time.time()

        self._battery_raw = self.battery.read()
        raw = self._battery_raw
        runtime, to_full = self._runtime_estimate(raw)
        battery = make_battery_info(raw, runtime, to_full)
        battery_status = self.battery.status(raw)

        rapl_w = self.rapl.read()
        rapl_status = self.rapl.status()
        meter_w = self.power_meter.read()
        meter_status = self.power_meter.status()
        if meter_w is None and meter_status.state == "warn":
            meter_status.state = "off"
            meter_status.summary = "无有效数据"

        nvml_state, nvml_age = self.gpu.latest()
        nvml_status = self.gpu.status()

        bg = self.processes.sample()
        cpu = self._cpu_from_rapl(rapl_w, rapl_status, bg.active_pct)
        gpu = self._gpu_from_nvml(nvml_state, nvml_age, nvml_status)

        total_w: float | None = None
        total_source = ""
        total_reason = ""
        total_label = ""
        if meter_w is not None and meter_w > 0.05:
            total_w = meter_w
            total_source = "Windows Power Meter"
            total_label = "EMI 整机功率"
        elif raw.discharging and raw.power_w is not None and raw.power_w > 0.05:
            total_w = raw.power_w
            total_source = "电池放电实测"
            total_label = "电池端直流"
        else:
            if raw.ac_online:
                total_reason = (
                    "插电状态：Windows Power Meter 无读数；本机没有其他真实整机功耗传感器。"
                    "电池无法测量整机输入功率，不使用 CPU+GPU 求和。"
                )
            elif raw.discharging:
                total_reason = "电池正在放电，但驱动未报告可用的放电功率。"
            elif not raw.ac_online and not raw.present:
                total_reason = "未检测到电池，且没有整机功耗传感器。"
            else:
                total_reason = "没有可用的整机功耗传感器（不使用 CPU+GPU 求和估算）。"

        bg_status = SourceStatus(
            "processes",
            "进程",
            "ok" if bg.active_pct is not None else "warn",
            f"采样 {bg.sampled_processes} 个进程" if bg.sampled_processes else "正在采样",
            bg.note,
            now,
        )

        source_sig = (
            f"{nvml_status.state}|{battery_status.state}|{bg_status.state}|"
            f"{rapl_status.state}|{meter_status.state}"
        )
        if source_sig != self._last_logged_sources:
            LOG.info(
                "Sources: NVML=%s (%s), Battery=%s (%s), RAPL=%s, PM=%s",
                nvml_status.summary,
                nvml_status.state,
                battery_status.summary,
                battery_status.state,
                rapl_status.state,
                meter_status.state,
            )
            self._last_logged_sources = source_sig

        nvml_status.extra["age"] = nvml_age
        nvml_status.extra["power_w"] = nvml_state.power_w
        nvml_status.extra["name"] = nvml_state.name
        battery_status.extra["health_pct"] = raw.health_pct
        battery_status.extra["cycles"] = raw.cycle_count
        rapl_status.extra["cpu_power_w"] = rapl_w
        meter_status.extra["total_power_w"] = meter_w

        return Snapshot(
            seq=self._seq,
            timestamp=now,
            total_w=total_w,
            total_source=total_source,
            total_reason=total_reason,
            total_label=total_label,
            cpu=cpu,
            gpu=gpu,
            battery=battery,
            background=bg,
            nvml=nvml_status,
            battery_source=battery_status,
            background_source=bg_status,
            rapl=rapl_status,
            power_meter=meter_status,
            refresh_s=self.interval,
        )


class DemoEngine:
    """Explicit demo source used only with --demo; never active by default."""

    def __init__(self, interval: float = 1.0) -> None:
        import math

        self.interval = interval
        self._math = math
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seq = 0
        self._t0 = time.time()
        self._latest = Snapshot(timestamp=time.time(), demo=True)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="Demo", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def latest(self) -> Snapshot:
        with self._lock:
            return self._latest

    def _run(self) -> None:
        processes = ProcessSampler()
        while not self._stop.is_set():
            self._seq += 1
            now = time.time()
            t = now - self._t0
            total = 47.0 + 7.0 * self._math.sin(t / 5.0) + 2.0 * self._math.sin(t / 1.7)
            cpu_w = 19.0 + 4.0 * self._math.sin(t / 3.3) + 1.4 * self._math.sin(t)
            bg = processes.sample()
            gpu_w = max(4.0, total - cpu_w - 8.0 - 1.5 * self._math.sin(t / 2.0))
            battery = BatteryInfo(
                present=True,
                ac_online=False,
                discharging=True,
                percent=max(5.0, 83.0 - (t / 1800.0) * 10),
                remaining_wh=max(5.0, 68.0 - (t / 1800.0) * 8),
                full_wh=80.0,
                design_wh=82.0,
                voltage_v=15.9,
                power_w=total,
                direction="discharging",
                runtime_seconds=68.0 / total * 3600.0,
                source="演示数据",
                health_pct=97.6,
                cycle_count=42,
            )
            snap = Snapshot(
                seq=self._seq,
                timestamp=now,
                total_w=total,
                total_source="演示数据",
                total_label="演示",
                cpu=CpuInfo(
                    name="Intel Core Ultra 9 275HX",
                    power_w=cpu_w,
                    temp_c=61.0 + self._math.sin(t / 5) * 4,
                    util_pct=bg.active_pct,
                    power_source="演示数据",
                ),
                gpu=GpuInfo(
                    name="NVIDIA GeForce RTX 5080 Laptop GPU",
                    power_w=gpu_w,
                    temp_c=55.0 + self._math.sin(t / 4) * 3,
                    util_pct=21.0 + 10.0 * self._math.sin(t / 3),
                    mem_util_pct=18.0,
                    source="演示数据",
                    nvml_ok=True,
                ),
                battery=battery,
                background=bg,
                nvml=SourceStatus("nvml", "NVIDIA", "ok", "演示模式", "演示数据", now),
                battery_source=SourceStatus("battery", "电池", "ok", "演示模式", "演示数据", now),
                background_source=SourceStatus(
                    "processes", "进程", "ok", "真实进程采样", bg.note, now
                ),
                rapl=SourceStatus("rapl", "RAPL CPU", "ok", "演示模式", "演示数据", now),
                power_meter=SourceStatus(
                    "power_meter", "Windows Power Meter", "off", "演示模式", "演示数据", now
                ),
                refresh_s=1.0,
                demo=True,
            )
            with self._lock:
                self._latest = snap
            self._stop.wait(self.interval)
