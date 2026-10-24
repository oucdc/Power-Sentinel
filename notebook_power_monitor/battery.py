"""Battery state through ACPI and the Windows WMI battery class.

The ACPI battery driver exposes design/full-charge capacity through its device
IOCTL.  On this laptop the dynamic status IOCTL returns an all-zero buffer, so
the live remaining capacity, voltage and charge/discharge rate are read from
the same ``root\\wmi:BatteryStatus`` provider that Windows itself uses.  Both
are real firmware-backed values; if neither reports power we return
``power_w=None`` rather than guessing from CPU/GPU power.
"""

from __future__ import annotations

import ctypes
import struct
import threading
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass

from .models import BatteryInfo, SourceStatus
from .util import LOG, clamp

GUID_DEVCLASS_BATTERY = "{72631E54-78A4-11D0-BCF7-00AA00B7B32A}"
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80

IOCTL_BATTERY_QUERY_TAG = 0x294040
IOCTL_BATTERY_QUERY_INFORMATION = 0x294044
IOCTL_BATTERY_QUERY_STATUS = 0x294048

BATTERY_INFORMATION_LEVEL = 0
BATTERY_CAPACITY_RELATIVE = 0x40000000
BATTERY_POWER_ON_LINE = 0x00000001
BATTERY_DISCHARGING = 0x00000002
BATTERY_CHARGING = 0x00000004
BATTERY_CRITICAL = 0x00000008

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_size_t),
    ]


class BATTERY_QUERY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BatteryTag", wintypes.ULONG),
        ("InformationLevel", wintypes.ULONG),
        ("AtRate", wintypes.LONG),
    ]


class BATTERY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Capabilities", wintypes.ULONG),
        ("Technology", wintypes.BYTE),
        ("Reserved", wintypes.BYTE * 3),
        ("Chemistry", wintypes.BYTE * 4),
        ("DesignedCapacity", wintypes.ULONG),
        ("FullChargedCapacity", wintypes.ULONG),
        ("DefaultAlert1", wintypes.ULONG),
        ("DefaultAlert2", wintypes.ULONG),
        ("CriticalBias", wintypes.ULONG),
        ("CycleCount", wintypes.ULONG),
    ]


class BATTERY_STATUS(ctypes.Structure):
    _fields_ = [
        ("PowerState", wintypes.ULONG),
        ("Capacity", wintypes.ULONG),
        ("Voltage", wintypes.ULONG),
        ("Rate", wintypes.LONG),
    ]


class BATTERY_WAIT_STATUS(ctypes.Structure):
    _fields_ = [
        ("BatteryTag", wintypes.ULONG),
        ("Timeout", wintypes.ULONG),
        ("PowerState", wintypes.ULONG),
        ("LowCapacity", wintypes.ULONG),
        ("HighCapacity", wintypes.ULONG),
    ]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUID),
    wintypes.LPCWSTR,
    wintypes.HWND,
    wintypes.DWORD,
]
setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(GUID),
    wintypes.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]

kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
kernel32.DeviceIoControl.restype = wintypes.BOOL
kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GetSystemPowerStatus.restype = wintypes.BOOL
kernel32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(SYSTEM_POWER_STATUS)]


@dataclass
class BatteryRaw:
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
    direction: str = "unknown"
    health_pct: float | None = None
    cycle_count: int | None = None
    reason: str = ""
    detail: str = ""
    source: str = ""
    timestamp: float = 0.0


def _guid(text: str) -> GUID:
    value = uuid.UUID(text)
    guid = GUID()
    guid.Data1 = value.time_low
    guid.Data2 = value.time_mid
    guid.Data3 = value.time_hi_version
    guid.Data4[:] = value.bytes[8:]
    return guid


def _power_status() -> tuple[bool | None, float | None, bool, str]:
    status = SYSTEM_POWER_STATUS()
    if not kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return None, None, False, "GetSystemPowerStatus 失败"
    ac: bool | None
    if status.ACLineStatus == 1:
        ac = True
    elif status.ACLineStatus == 0:
        ac = False
    else:
        ac = None
    percent = float(status.BatteryLifePercent) if status.BatteryLifePercent != 255 else None
    no_battery = bool(status.BatteryFlag & 0x80)
    return ac, percent, not no_battery, ""


class _WmiBattery:
    """Small, reused WMI client for root\\wmi:BatteryStatus.

    ``wmi`` is imported lazily so the rest of the module (and the source-tree
    diagnostics) remain usable if pywin32 is not installed.  COM is initialised
    on the collector thread that performs the queries.
    """

    def __init__(self) -> None:
        self._client = None
        self._thread_id: int | None = None
        self._error = ""
        self._logged = False

    @property
    def error(self) -> str:
        return self._error

    def read(self) -> dict | None:
        try:
            import pythoncom
            import wmi
        except Exception as exc:
            self._error = f"WMI 组件不可用：{exc}"
            return None
        ident = threading.get_ident()
        if self._thread_id != ident:
            try:
                pythoncom.CoInitialize()
            except Exception:
                pass
            self._client = None
            self._thread_id = ident
        try:
            if self._client is None:
                self._client = wmi.WMI(namespace="root\\wmi")
            rows = list(self._client.BatteryStatus())
            if not rows:
                self._error = "WMI 未返回 BatteryStatus"
                return None

            def number(obj, name: str) -> int:
                try:
                    value = getattr(obj, name, 0)
                    return int(value or 0)
                except (TypeError, ValueError):
                    return 0

            row = max(rows, key=lambda item: number(item, "RemainingCapacity"))
            remaining = number(row, "RemainingCapacity")
            charge_rate = number(row, "ChargeRate")
            discharge_rate = number(row, "DischargeRate")
            voltage = number(row, "Voltage")
            valid_remaining = 0 <= remaining <= 300_000
            valid_rate = 0 <= charge_rate <= 300_000 and 0 <= discharge_rate <= 300_000
            valid_voltage = 1_000 <= voltage <= 30_000
            if not (valid_remaining or valid_rate or valid_voltage):
                self._error = "WMI BatteryStatus 返回无效数值"
                return None
            self._error = ""
            return {
                "remaining_mwh": remaining if valid_remaining else None,
                "charge_rate_mw": charge_rate if valid_rate else None,
                "discharge_rate_mw": discharge_rate if valid_rate else None,
                "voltage_mv": voltage if valid_voltage else None,
                "charging": bool(getattr(row, "Charging", False)),
                "discharging": bool(getattr(row, "Discharging", False)),
                "power_online": (
                    bool(row.PowerOnline) if getattr(row, "PowerOnline", None) is not None else None
                ),
            }
        except Exception as exc:
            self._error = f"WMI BatteryStatus 查询失败：{exc}"
            self._client = None
            if not self._logged:
                LOG.warning("WMI BatteryStatus query failed; using ACPI fallback: %s", exc)
                self._logged = True
            return None


class BatteryReader:
    def __init__(self) -> None:
        self._handle: int | None = None
        self._path = ""
        self._tag: int | None = None
        self._info: BATTERY_INFORMATION | None = None
        self._info_ts = 0.0
        self._last_raw: BatteryRaw | None = None
        self._wmi = _WmiBattery()
        self.last_error = ""
        self.last_success = 0.0

    def close(self) -> None:
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None
        self._path = ""
        self._tag = None
        self._info = None

    def _find_path(self) -> str | None:
        guid = _guid(GUID_DEVCLASS_BATTERY)
        flags = DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        info_set = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, flags)
        if not info_set or info_set == INVALID_HANDLE_VALUE:
            self.last_error = f"无法枚举电池设备 (WinError {ctypes.get_last_error()})"
            return None
        interface = SP_DEVICE_INTERFACE_DATA()
        interface.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
        try:
            if not setupapi.SetupDiEnumDeviceInterfaces(
                info_set, None, ctypes.byref(guid), 0, ctypes.byref(interface)
            ):
                self.last_error = f"没有可用的电池接口 (WinError {ctypes.get_last_error()})"
                return None
            required = wintypes.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                info_set,
                ctypes.byref(interface),
                None,
                0,
                ctypes.byref(required),
                None,
            )
            if required.value < 8:
                self.last_error = "电池设备路径查询失败"
                return None
            buf = ctypes.create_string_buffer(required.value)
            # cbSize is the DWORD size field (8 on 64-bit Windows).
            struct.pack_into("<I", buf, 0, 8)
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                info_set,
                ctypes.byref(interface),
                buf,
                required.value,
                ctypes.byref(required),
                None,
            ):
                self.last_error = f"读取电池设备路径失败 (WinError {ctypes.get_last_error()})"
                return None
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            return path or None
        finally:
            setupapi.SetupDiDestroyDeviceInfoList(info_set)

    def _open(self) -> bool:
        if self._handle:
            return True
        path = self._find_path()
        if not path:
            return False
        for access in (GENERIC_READ, GENERIC_READ | GENERIC_WRITE):
            handle = kernel32.CreateFileW(
                path,
                access,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                None,
            )
            if handle and handle != INVALID_HANDLE_VALUE:
                self._handle = handle
                self._path = path
                self.last_error = ""
                return True
        self.last_error = f"无法打开电池设备 (WinError {ctypes.get_last_error()})"
        return False

    def _ioctl(self, code: int, in_buf, in_size: int, out_buf, out_size: int) -> bool:
        if not self._handle:
            return False
        returned = wintypes.DWORD(0)
        return bool(
            kernel32.DeviceIoControl(
                self._handle,
                code,
                in_buf,
                in_size,
                out_buf,
                out_size,
                ctypes.byref(returned),
                None,
            )
        )

    def _query_tag(self) -> int | None:
        if not self._handle:
            return None
        tag = wintypes.ULONG(0)
        if not self._ioctl(IOCTL_BATTERY_QUERY_TAG, None, 0, ctypes.byref(tag), ctypes.sizeof(tag)):
            return None
        return int(tag.value)

    def _query_info(self, tag: int) -> BATTERY_INFORMATION | None:
        query = BATTERY_QUERY_INFORMATION()
        query.BatteryTag = tag
        query.InformationLevel = BATTERY_INFORMATION_LEVEL
        query.AtRate = 0
        info = BATTERY_INFORMATION()
        if not self._ioctl(
            IOCTL_BATTERY_QUERY_INFORMATION,
            ctypes.byref(query),
            ctypes.sizeof(query),
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            return None
        return info

    def _query_status(self, tag: int) -> BATTERY_STATUS | None:
        wait = BATTERY_WAIT_STATUS()
        wait.BatteryTag = tag
        wait.Timeout = 0
        wait.PowerState = 0xFFFFFFFF
        wait.LowCapacity = 0
        wait.HighCapacity = 0xFFFFFFFF
        status = BATTERY_STATUS()
        if not self._ioctl(
            IOCTL_BATTERY_QUERY_STATUS,
            ctypes.byref(wait),
            ctypes.sizeof(wait),
            ctypes.byref(status),
            ctypes.sizeof(status),
        ):
            return None
        return status

    def read(self) -> BatteryRaw:
        ac, percent_fallback, present_fallback, ps_error = _power_status()
        now = time.time()

        info: BATTERY_INFORMATION | None = None
        tag: int | None = None
        opened = self._open()
        if opened:
            tag = self._query_tag()
            if tag is None:
                self.last_error = f"QueryTag 失败 (WinError {ctypes.get_last_error()})"
                self.close()
            else:
                if self._tag != tag or self._info is None or now - self._info_ts > 60:
                    new_info = self._query_info(tag)
                    if new_info is not None:
                        self._tag = tag
                        self._info = new_info
                        self._info_ts = now
                info = self._info

        wmi = self._wmi.read()
        io_status: BATTERY_STATUS | None = None
        remaining_mwh: int | None = None
        voltage_mv: int | None = None
        charging = False
        discharging = False
        dynamic_source = ""

        if wmi is not None:
            charging = bool(wmi["charging"])
            discharging = bool(wmi["discharging"])
            if ac is None and wmi.get("power_online") is not None:
                ac = bool(wmi["power_online"])
            charge_rate = int(wmi.get("charge_rate_mw") or 0)
            discharge_rate = int(wmi.get("discharge_rate_mw") or 0)
            if not charging and not discharging:
                if ac is True and charge_rate > 0:
                    charging = True
                elif ac is False and discharge_rate > 0:
                    discharging = True
            if charging and discharging:
                discharging = False
            remaining_mwh = wmi.get("remaining_mwh")
            voltage_mv = wmi.get("voltage_mv")
            rate_mw = charge_rate if charging else (discharge_rate if discharging else 0)
            dynamic_source = "WMI BatteryStatus"
            self.last_error = self._wmi.error
        elif opened and tag is not None:
            io_status = self._query_status(tag)
            if io_status is not None:
                nonzero = (
                    io_status.Capacity > 0
                    or io_status.Voltage > 0
                    or io_status.Rate != 0
                    or io_status.PowerState != 0
                )
                if not nonzero:
                    io_status = None
            if io_status is not None:
                power_state = int(io_status.PowerState)
                charging = bool(power_state & BATTERY_CHARGING)
                discharging = bool(power_state & BATTERY_DISCHARGING)
                if ac is None:
                    ac = bool(power_state & BATTERY_POWER_ON_LINE)
                if charging and discharging:
                    discharging = False
                if 0 < io_status.Capacity <= 300_000:
                    remaining_mwh = int(io_status.Capacity)
                if 1_000 <= io_status.Voltage <= 30_000:
                    voltage_mv = int(io_status.Voltage)
                rate_mw = abs(int(io_status.Rate))
                dynamic_source = "ACPI battery IOCTL"
                self.last_error = ""

        if not dynamic_source:
            detail = " · ".join(
                bit
                for bit in (
                    self.last_error,
                    self._wmi.error,
                    ps_error,
                    "电池动态状态接口未返回有效数据",
                )
                if bit
            )
            raw = BatteryRaw(
                present=present_fallback or opened,
                ac_online=ac,
                percent=percent_fallback,
                direction="unknown",
                reason="电池状态接口未报告容量/功率",
                detail=detail,
                source="ACPI/WMI",
                timestamp=now,
            )
            self._last_raw = raw
            return raw

        capacity_relative = bool(info and (info.Capabilities & BATTERY_CAPACITY_RELATIVE))
        full_wh = None
        design_wh = None
        health = None
        cycles = None
        if info and not capacity_relative:
            if 100 <= info.DesignedCapacity <= 300_000:
                design_wh = info.DesignedCapacity / 1000.0
            if 100 <= info.FullChargedCapacity <= 300_000:
                full_wh = info.FullChargedCapacity / 1000.0
            if design_wh and full_wh:
                health = clamp(full_wh / design_wh * 100.0, 0.0, 150.0)
            if 0 < info.CycleCount < 100_000:
                cycles = int(info.CycleCount)

        remaining_wh = None
        if not capacity_relative and remaining_mwh is not None and 0 <= remaining_mwh <= 300_000:
            remaining_wh = remaining_mwh / 1000.0

        percent = percent_fallback
        if remaining_wh is not None and full_wh:
            percent = clamp(remaining_wh / full_wh * 100.0, 0.0, 100.0)
        elif remaining_wh is not None and percent_fallback is None:
            percent = None

        voltage = voltage_mv / 1000.0 if voltage_mv and 1_000 <= voltage_mv <= 30_000 else None

        rate_w = abs(float(rate_mw)) / 1000.0 if dynamic_source else 0.0
        if rate_w > 300.0:
            rate_w = 0.0
        power_w: float | None = None
        if charging or discharging:
            if rate_w >= 0.05:
                power_w = rate_w
        if charging:
            direction = "charging"
        elif discharging:
            direction = "discharging"
        elif ac:
            direction = "idle"
        else:
            direction = "unknown"

        reason = ""
        detail_bits = [dynamic_source]
        if not info:
            detail_bits.append("BATTERY_INFORMATION 不可用")
        if power_w is None and direction in ("charging", "discharging"):
            reason = "电池未报告充放电功率"
            detail_bits.append("驱动 Rate=0")
        elif direction == "idle":
            reason = "电池当前未充放电" if ac else "电池未在放电"
        elif direction == "unknown":
            reason = "电池未在放电且状态未知"
        if not info and self.last_error:
            detail_bits.append(self.last_error)
        self.last_success = now

        raw = BatteryRaw(
            present=True,
            ac_online=ac,
            charging=charging,
            discharging=discharging,
            percent=percent,
            remaining_wh=remaining_wh,
            full_wh=full_wh,
            design_wh=design_wh,
            voltage_v=voltage,
            power_w=power_w,
            direction=direction,
            health_pct=health,
            cycle_count=cycles,
            reason=reason,
            detail=" · ".join(detail_bits) or f"电池设备：{self._path}",
            source=f"{dynamic_source} + ACPI",
            timestamp=now,
        )
        self._last_raw = raw
        return raw

    def status(self, raw: BatteryRaw | None = None) -> SourceStatus:
        raw = raw or self._last_raw
        time.time()
        if raw is None:
            return SourceStatus("battery", "电池", "off", "尚未读取", self.last_error)
        if not raw.present:
            return SourceStatus(
                "battery",
                "电池",
                "warn",
                "未检测到电池",
                raw.detail or "设备可能为台式机或电池被禁用。",
                raw.timestamp,
            )
        if raw.remaining_wh is None and raw.percent is None:
            return SourceStatus(
                "battery",
                "电池",
                "warn",
                "容量不可用",
                raw.detail or raw.reason,
                raw.timestamp,
            )
        bits = []
        if raw.remaining_wh is not None:
            bits.append(f"当前 {raw.remaining_wh:.1f} Wh")
        if raw.ac_online is not None:
            bits.append("已接电源" if raw.ac_online else "电池供电")
        if raw.direction == "charging" and raw.power_w is not None:
            bits.append(f"充电 {raw.power_w:.1f} W")
        elif raw.direction == "discharging" and raw.power_w is not None:
            bits.append(f"放电 {raw.power_w:.1f} W")
        detail = " · ".join(bits) or (raw.detail or "电池数据可用")
        summary = "实时读取"
        if raw.power_w is None and raw.direction in ("charging", "discharging"):
            summary = "容量可用 · 功率不可用"
        return SourceStatus(
            "battery",
            "电池",
            "ok" if raw.power_w is not None or raw.remaining_wh is not None else "warn",
            summary,
            detail,
            raw.timestamp,
            extra={
                "present": raw.present,
                "remaining_wh": raw.remaining_wh,
                "full_wh": raw.full_wh,
                "power_w": raw.power_w,
                "direction": raw.direction,
            },
        )


def make_battery_info(
    raw: BatteryRaw, runtime_s: float | None, time_full_s: float | None
) -> BatteryInfo:
    return BatteryInfo(
        present=raw.present,
        ac_online=raw.ac_online,
        charging=raw.charging,
        discharging=raw.discharging,
        percent=raw.percent,
        remaining_wh=raw.remaining_wh,
        full_wh=raw.full_wh,
        design_wh=raw.design_wh,
        source=raw.source or "ACPI 电池",
        voltage_v=raw.voltage_v,
        power_w=raw.power_w,
        direction=raw.direction,
        runtime_seconds=runtime_s,
        time_to_full_seconds=time_full_s,
        reason=raw.reason,
        health_pct=raw.health_pct,
        cycle_count=raw.cycle_count,
    )
