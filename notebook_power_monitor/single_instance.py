"""Single-instance activation via a named mutex/event.

A second double-click sends a signal to the already-running instance (which may
be hidden in the notification area) and exits before creating a second Tk
application / tray icon.
"""

from __future__ import annotations

import ctypes
import threading
from collections.abc import Callable
from ctypes import wintypes

from .util import LOG

ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0
MUTEX_NAME = r"Local\NotebookPowerMonitor.SingleInstance"
EVENT_NAME = r"Local\NotebookPowerMonitor.Show"


class SingleInstance:
    def __init__(self) -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateEventW.restype = wintypes.HANDLE
        self._kernel32.CreateEventW.argtypes = [
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        self._kernel32.CreateMutexW.restype = wintypes.HANDLE
        self._kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        self._kernel32.OpenEventW.restype = wintypes.HANDLE
        self._kernel32.OpenEventW.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        self._kernel32.SetEvent.restype = wintypes.BOOL
        self._kernel32.SetEvent.argtypes = [wintypes.HANDLE]
        self._kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self._kernel32.WaitForSingleObject.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
        ]
        self._kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        ctypes.set_last_error(0)
        self._event = self._kernel32.CreateEventW(None, False, False, EVENT_NAME)
        self._mutex = self._kernel32.CreateMutexW(None, True, MUTEX_NAME)
        self._already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def already_running(self) -> bool:
        return self._already_running

    def signal_existing(self) -> None:
        event = self._event
        if not event:
            event = self._kernel32.OpenEventW(0x0002, False, EVENT_NAME)
        if event:
            self._kernel32.SetEvent(event)
            if event != self._event:
                self._kernel32.CloseHandle(event)

    def start_listener(self, callback: Callable[[], None]) -> None:
        if self._already_running or not self._event:
            return

        def worker() -> None:
            while not self._stop.is_set():
                result = self._kernel32.WaitForSingleObject(self._event, 500)
                if result == WAIT_OBJECT_0:
                    try:
                        callback()
                    except Exception:
                        LOG.exception("Single-instance activation callback failed")

        self._thread = threading.Thread(target=worker, name="SingleInstance", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        if self._mutex:
            self._kernel32.CloseHandle(self._mutex)
            self._mutex = None
        if self._event:
            self._kernel32.CloseHandle(self._event)
            self._event = None
