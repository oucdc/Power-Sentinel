"""Data models shared by the collectors and the UI.

The monitor deliberately keeps "unavailable" separate from 0.0 W.  A missing
sensor must never look like a measured reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceStatus:
    """Health of one physical data source."""

    key: str
    label: str
    state: str  # ok | warn | error | off
    summary: str
    detail: str = ""
    last_update: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def is_ok(self) -> bool:
        return self.state == "ok"


@dataclass
class CpuInfo:
    name: str = "CPU"
    power_w: float | None = None
    temp_c: float | None = None
    util_pct: float | None = None
    power_source: str = ""
    power_reason: str = ""
    power_detail: str = ""
    clock_mhz: float | None = None


@dataclass
class GpuInfo:
    name: str = "GPU"
    power_w: float | None = None
    temp_c: float | None = None
    util_pct: float | None = None
    mem_util_pct: float | None = None
    source: str = ""
    reason: str = ""
    nvml_ok: bool = False
    power_detail: str = ""


@dataclass
class BatteryInfo:
    present: bool = False
    ac_online: bool | None = None
    charging: bool = False
    discharging: bool = False
    percent: float | None = None
    remaining_wh: float | None = None
    full_wh: float | None = None
    design_wh: float | None = None
    voltage_v: float | None = None
    power_w: float | None = None
    direction: str = "unknown"  # charging | discharging | idle | unknown
    runtime_seconds: float | None = None
    time_to_full_seconds: float | None = None
    source: str = ""
    reason: str = ""
    health_pct: float | None = None
    cycle_count: int | None = None


@dataclass
class ProcessLoad:
    pid: int
    name: str
    cpu_pct: float


@dataclass
class BackgroundInfo:
    # Active CPU of the entire machine (Idle excluded).
    active_pct: float | None = None
    # CPU of every non-idle, non-foreground process, normalised to all cores.
    background_pct: float | None = None
    # background_pct / active_pct * 100 (the "share" view).
    share_of_active_pct: float | None = None
    foreground_name: str = ""
    foreground_excluded: bool = False
    top: list[ProcessLoad] = field(default_factory=list)
    note: str = ""
    foreground_pid: int = 0
    sampled_processes: int = 0


@dataclass
class Snapshot:
    seq: int = 0
    timestamp: float = 0.0
    total_w: float | None = None
    total_source: str = ""
    total_reason: str = ""
    total_label: str = ""
    total_kind: str = ""
    cpu: CpuInfo = field(default_factory=CpuInfo)
    gpu: GpuInfo = field(default_factory=GpuInfo)
    battery: BatteryInfo = field(default_factory=BatteryInfo)
    background: BackgroundInfo = field(default_factory=BackgroundInfo)
    nvml: SourceStatus = field(
        default_factory=lambda: SourceStatus("nvml", "NVIDIA", "off", "未连接")
    )
    battery_source: SourceStatus = field(
        default_factory=lambda: SourceStatus("battery", "电池", "off", "未连接")
    )
    background_source: SourceStatus = field(
        default_factory=lambda: SourceStatus("processes", "进程", "off", "正在采样")
    )
    rapl: SourceStatus = field(
        default_factory=lambda: SourceStatus("rapl", "RAPL CPU", "off", "未连接")
    )
    power_meter: SourceStatus = field(
        default_factory=lambda: SourceStatus("power_meter", "Windows Power Meter", "off", "不可用")
    )
    refresh_s: float = 1.0
    demo: bool = False

    @property
    def foreground_label(self) -> str:
        return self.background.foreground_name or "前台窗口"


@dataclass
class GpuNvmlReading:
    """One live NVML sample; never persisted across a failed query."""

    available: bool = False
    name: str = "NVIDIA GPU"
    power_w: float | None = None
    temp_c: float | None = None
    util_pct: float | None = None
    mem_util_pct: float | None = None
    error: str = ""
    timestamp: float = 0.0
    device_index: int = 0
