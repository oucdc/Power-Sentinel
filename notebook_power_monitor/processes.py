"""Windows process inventory and CPU accounting.

All process percentages are normalised to the whole machine (0..100), never to
one core.  PID 0 / System Idle Process is explicitly excluded.  The aggregate
background value is derived from kernel system times so it can never exceed
100% even when some protected processes cannot be opened.
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass

from .models import BackgroundInfo, ProcessLoad
from .util import clamp

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_PATH = 260


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.GetProcessTimes.restype = wintypes.BOOL
kernel32.GetProcessTimes.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
]
kernel32.GetSystemTimes.restype = wintypes.BOOL
kernel32.GetSystemTimes.argtypes = [
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
]

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]


def _filetime_to_int(ft: wintypes.FILETIME) -> int:
    return (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)


@dataclass(frozen=True)
class ProcessEntry:
    pid: int
    name: str


def iter_processes() -> list[ProcessEntry]:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE or not snap:
        return []
    entries: list[ProcessEntry] = []
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    try:
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            entries.append(ProcessEntry(int(entry.th32ProcessID), entry.szExeFile))
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return entries


def foreground_window() -> tuple[int, str]:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0, ""
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    length = user32.GetWindowTextLengthW(hwnd)
    title = ""
    if 0 < length < 1024:
        buf = ctypes.create_unicode_buffer(length + 2)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
    return int(pid.value), title


class SystemCpu:
    """Delta of GetSystemTimes, returning whole-machine active CPU."""

    def __init__(self) -> None:
        self._last: tuple[int, int, int] | None = None

    def sample(self) -> float | None:
        idle = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        ):
            return None
        current = (
            _filetime_to_int(idle),
            _filetime_to_int(kernel),
            _filetime_to_int(user),
        )
        previous = self._last
        self._last = current
        if previous is None:
            return None
        idle_d = current[0] - previous[0]
        kernel_d = current[1] - previous[1]
        user_d = current[2] - previous[2]
        total = kernel_d + user_d  # kernel includes idle
        if total <= 0:
            return None
        active = total - idle_d
        return clamp(active * 100.0 / total, 0.0, 100.0)


@dataclass
class _ProcTimes:
    created: int
    cpu_100ns: int
    pct: float


class ProcessSampler:
    def __init__(self) -> None:
        self._previous: dict[int, tuple[int, int]] = {}
        self._last_ts: float | None = None
        self._system = SystemCpu()
        self._cpu_count = max(1, os.cpu_count() or 1)
        self._last_samples: dict[int, _ProcTimes] = {}
        self._last_names: dict[int, str] = {}
        self._first = True

    @property
    def last_process_names(self) -> dict[int, str]:
        return dict(self._last_names)

    def _read_times(self, pid: int) -> tuple[int, int] | None:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_ft = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_ft),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return None
            return (
                _filetime_to_int(creation),
                _filetime_to_int(kernel) + _filetime_to_int(user),
            )
        finally:
            kernel32.CloseHandle(handle)

    def sample(self) -> BackgroundInfo:
        now = time.monotonic()
        prev_ts = self._last_ts
        elapsed = (now - prev_ts) if prev_ts else 0.0
        active = self._system.sample()
        entries = iter_processes()
        names = {e.pid: e.name for e in entries}
        self._last_names = names
        fg_pid, _ = foreground_window()

        current_raw: dict[int, tuple[int, int]] = {}
        current_pct: dict[int, float] = {}
        for entry in entries:
            pid = entry.pid
            if pid == 0 or entry.name.lower() == "system idle process":
                continue
            times = self._read_times(pid)
            if times is None:
                continue
            current_raw[pid] = times
            previous = self._previous.get(pid)
            if previous is not None and elapsed > 0.05 and previous[0] == times[0]:
                delta = times[1] - previous[1]
                if delta >= 0:
                    pct = delta / 10_000_000.0 / elapsed
                    pct = pct / self._cpu_count * 100.0
                    current_pct[pid] = clamp(pct, 0.0, 100.0)

        self._previous = current_raw
        self._last_ts = now
        first = self._first
        self._first = False

        fg_name = names.get(fg_pid, f"PID {fg_pid}" if fg_pid else "")
        if fg_name.lower().endswith(".exe"):
            fg_name = fg_name[:-4]
        fg_pct = current_pct.get(fg_pid, 0.0) if fg_pid else 0.0

        if active is None:
            active = None
            background = None
            share = None
        else:
            background = clamp(active - fg_pct, 0.0, 100.0)
            share = clamp(background * 100.0 / active, 0.0, 100.0) if active > 0.1 else 0.0

        top: list[ProcessLoad] = []
        if not first and elapsed > 0.05:
            for pid, pct in current_pct.items():
                if pid == fg_pid:
                    continue
                if pct < 0.03:
                    continue
                raw = names.get(pid, str(pid))
                if raw.lower() == "system idle process":
                    continue
                top.append(ProcessLoad(pid=pid, name=raw, cpu_pct=round(pct, 2)))
            top.sort(key=lambda item: item.cpu_pct, reverse=True)
            top = top[:5]

        note = f"已排除 System Idle Process 与前台应用；按 {self._cpu_count} 个逻辑线程归一化"
        if first:
            note = "正在采样进程占用（约 1 秒）"
        if active is None:
            note = "CPU 利用率暂不可用"

        return BackgroundInfo(
            active_pct=round(active, 2) if active is not None else None,
            background_pct=round(background, 2) if background is not None else None,
            share_of_active_pct=round(share, 2) if share is not None else None,
            foreground_name=fg_name,
            foreground_excluded=bool(fg_pid),
            top=top,
            note=note,
            foreground_pid=fg_pid,
            sampled_processes=len(current_pct),
        )


def process_display_name(pid: int) -> str:
    if pid == 0:
        return "System Idle Process"
    for entry in iter_processes():
        if entry.pid == pid:
            name = entry.name
            return name[:-4] if name.lower().endswith(".exe") else name
    return f"PID {pid}"
