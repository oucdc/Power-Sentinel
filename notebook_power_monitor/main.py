"""Application shell, window lifecycle and refresh loop."""

from __future__ import annotations

import ctypes
import queue
import re
import sys
import tempfile
import time
import tkinter as tk
import traceback
from collections import deque
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox

from .collector import DemoEngine, MonitoringEngine
from .config import Config
from .dialogs import SourceDialog
from .floating import FloatingBar
from .models import Snapshot
from .single_instance import SingleInstance
from .tray import TrayController
from .ui_cards import (
    BatteryCard,
    ChartCard,
    CpuCard,
    FooterBar,
    GpuCard,
    HeaderBar,
    ProcessCard,
    TotalCard,
)
from .ui_theme import BG, Theme
from .util import (
    APP_NAME,
    APP_VERSION,
    LOG,
    app_data_dir,
    resource_icon_path,
)


def setup_dpi_awareness() -> None:
    # Per-monitor V2 keeps the app on the primary monitor from being bitmap
    # scaled when the user has a 150% secondary display.  Fall back gracefully
    # on older Windows versions.
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def primary_work_area() -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    user32.MonitorFromPoint.restype = ctypes.c_void_p
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    point = wintypes.POINT(0, 0)
    monitor = user32.MonitorFromPoint(point, 1)  # MONITOR_DEFAULTTOPRIMARY
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        rc = info.rcWork
        return rc.left, rc.top, rc.right, rc.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def set_app_user_model_id() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Mechrevo.NotebookPowerMonitor"
        )
    except Exception:
        pass


def dark_title_bar(window: tk.Misc) -> None:
    try:
        window.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.GetAncestor.argtypes = [ctypes.c_void_p, wintypes.UINT]
        hwnd = int(window.winfo_id())
        root_hwnd = user32.GetAncestor(hwnd, 2) or hwnd
        value = ctypes.c_int(1)
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                root_hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                break
    except Exception:
        pass


def _screen_geometry(theme: Theme) -> tuple[int, int, int, int]:
    sw = theme.root.winfo_screenwidth()
    sh = theme.root.winfo_screenheight()
    width = min(theme.s(1180), sw - theme.s(40))
    height = min(theme.s(800), sh - theme.s(110))
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 2 - theme.s(18))
    return width, height, x, y


class PowerMonitorApp:
    def __init__(
        self,
        root: tk.Tk,
        config: Config,
        engine: MonitoringEngine | DemoEngine,
        demo: bool = False,
        single_instance: SingleInstance | None = None,
    ) -> None:
        self.root = root
        self.config = config
        self.engine = engine
        self.demo = demo
        self._closing = False
        self._tick_job: str | None = None
        self.single_instance = single_instance
        self._last_seq = -1
        self._stale = False
        self._last_render_stale = False
        self._history: deque[tuple[float | None, float | None, float | None]] = deque(maxlen=90)
        self._last_tray_update = 0.0
        self._source_dialog: SourceDialog | None = None
        self._tray_hint_shown = False
        self._ui_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._primary_positioned = False
        self.icon_path = resource_icon_path()
        self.theme = Theme(root)
        self.tray = TrayController(self, self.icon_path)
        self.floating: FloatingBar | None = None
        self.header: HeaderBar | None = None
        self.source_button: tk.Widget | None = None

        root.title(f"{APP_NAME} · Notebook Power Monitor")
        if demo:
            root.title("电量哨兵 · 演示模式（非真实读数）")
        root.configure(bg=BG)
        root.option_add("*tearOff", False)
        if self.icon_path:
            try:
                root.iconbitmap(default=str(self.icon_path))
            except Exception:
                pass
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.report_callback_exception = self._report_callback_exception
        root.bind("<F1>", lambda _e: self.show_sources())
        root.bind("<Control-Shift-F>", lambda _e: self.toggle_floating())
        root.bind("<Control-q>", lambda _e: self.quit_app())

        self._build_window_geometry()
        self._build_ui()
        self._build_floating()
        self._restore_zoomed()

        self.engine.start()
        if self.single_instance is not None:
            self.single_instance.start_listener(lambda: self.post(self.show_main))
        self.root.after(120, lambda: self._center_on_primary(force=True))
        self.root.after(900, lambda: self._center_on_primary(force=False))
        self.root.after(500, self._start_tray)
        self.root.after(300, self._tick)
        self.root.after(220, lambda: dark_title_bar(self.root))
        if self.config.get("floating_visible", True):
            self.root.after(260, self._show_initial_floating)
        initial = self.engine.latest()
        self._last_seq = initial.seq
        if self.header:
            self.header.update_status(initial, stale=False)
            self.header.set_floating_visible(bool(self.floating and self.floating.visible))
        if hasattr(self, "footer"):
            self.footer.update(initial, stale=False)
        LOG.info("%s %s started (demo=%s)", APP_NAME, APP_VERSION, demo)

    # -- construction --------------------------------------------------
    def _build_window_geometry(self) -> None:
        theme = self.theme
        width, height, x, y = _screen_geometry(theme)
        geometry = self.config.get("main_geometry") or ""
        match = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", str(geometry))
        if match:
            w, h, gx, gy = (int(part) for part in match.groups())
            if w >= theme.s(980) and h >= theme.s(680):
                sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                x = max(0, min(gx, sw - theme.s(240)))
                y = max(0, min(gy, sh - theme.s(160)))
                width, height = min(w, sw), min(h, sh)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        min_w = min(theme.s(1060), self.root.winfo_screenwidth() - theme.s(24))
        min_h = min(theme.s(720), self.root.winfo_screenheight() - theme.s(70))
        self.root.minsize(max(theme.s(900), min_w), max(theme.s(620), min_h))
        LOG.info(
            "Tk screen=%sx%s dpi=%.0f scale=%.2f geometry=%s",
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
            self.root.winfo_fpixels("1i"),
            theme.scale,
            self.root.geometry(),
        )

    def _center_on_primary(self, force: bool) -> None:
        """Place the initial window on the primary monitor.

        Tk can be launched by the shell on a 150%-scaled secondary monitor and
        Windows may bitmap-scale it there.  Explicitly centering on the primary
        work area keeps the first launch predictable on mixed-DPI setups.
        """
        if self._primary_positioned and not force:
            return
        if self.config.get("main_geometry") or self.config.get("main_zoomed"):
            self._primary_positioned = True
            return
        try:
            self.root.update_idletasks()
            user32 = ctypes.windll.user32
            user32.GetWindowRect.restype = wintypes.BOOL
            user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
            user32.GetAncestor.restype = ctypes.c_void_p
            user32.GetAncestor.argtypes = [ctypes.c_void_p, wintypes.UINT]
            user32.SetWindowPos.restype = wintypes.BOOL
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            hwnd = int(self.root.winfo_id())
            root_hwnd = user32.GetAncestor(hwnd, 2) or hwnd
            rect = wintypes.RECT()
            if not user32.GetWindowRect(root_hwnd, ctypes.byref(rect)):
                return
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w <= 0 or h <= 0:
                return
            left, top, right, bottom = primary_work_area()
            work_w, work_h = right - left, bottom - top
            if w > work_w:
                w = work_w
            if h > work_h:
                h = work_h
            x = left + max(0, (work_w - w) // 2)
            y = top + max(0, (work_h - h) // 2)
            # NOSIZE | NOZORDER | NOACTIVATE: Tk remains responsible for the
            # client size; only the window origin moves.
            user32.SetWindowPos(root_hwnd, None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)
            self.root.update_idletasks()
            actual = wintypes.RECT()
            user32.GetWindowRect(root_hwnd, ctypes.byref(actual))
            LOG.info(
                "Primary placement: work=%s,%s %sx%s window_size=%sx%s actual=%sx%s at %s,%s",
                left,
                top,
                work_w,
                work_h,
                w,
                h,
                actual.right - actual.left,
                actual.bottom - actual.top,
                actual.left,
                actual.top,
            )
            self._primary_positioned = True
        except Exception:
            LOG.exception("Could not center the main window on the primary monitor")

    def _build_ui(self) -> None:
        theme = self.theme
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True, padx=theme.s(20), pady=(theme.s(14), theme.s(12)))

        self.header = HeaderBar(
            shell,
            theme,
            on_sources=self.show_sources,
            on_floating=self.toggle_floating,
        )
        self.header.pack(fill="x")
        self.header.set_floating_visible(False)

        self.footer = FooterBar(shell, theme)
        self.footer.pack(side="bottom", fill="x", pady=(theme.s(8), 0))

        content = tk.Frame(shell, bg=BG)
        content.pack(fill="both", expand=True, pady=(theme.s(12), 0))
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        top = tk.Frame(content, bg=BG)
        top.grid(row=0, column=0, sticky="nsew")
        top.grid_columnconfigure(0, weight=4, uniform="top")
        top.grid_columnconfigure(1, weight=3, uniform="top")
        top.grid_columnconfigure(2, weight=3, uniform="top")
        top.grid_rowconfigure(0, weight=1)

        self.total_card = TotalCard(top, theme)
        self.total_card.grid(row=0, column=0, sticky="nsew", padx=(0, theme.s(12)))
        self.cpu_card = CpuCard(top, theme)
        self.cpu_card.grid(row=0, column=1, sticky="nsew", padx=(0, theme.s(12)))
        self.gpu_card = GpuCard(top, theme)
        self.gpu_card.grid(row=0, column=2, sticky="nsew")

        mid = tk.Frame(content, bg=BG)
        mid.grid(row=1, column=0, sticky="nsew", pady=(theme.s(12), 0))
        mid.grid_columnconfigure(0, weight=4, uniform="mid")
        mid.grid_columnconfigure(1, weight=6, uniform="mid")
        mid.grid_rowconfigure(0, weight=1)
        self.battery_card = BatteryCard(mid, theme)
        self.battery_card.grid(row=0, column=0, sticky="nsew", padx=(0, theme.s(12)))
        self.process_card = ProcessCard(mid, theme)
        self.process_card.grid(row=0, column=1, sticky="nsew")

        self.chart_card = ChartCard(content, theme)
        self.chart_card.grid(row=2, column=0, sticky="nsew", pady=(theme.s(12), 0))

    def _build_floating(self) -> None:
        self.floating = FloatingBar(self, self.root, self.theme)
        self.header.set_floating_visible(False)

    def _restore_zoomed(self) -> None:
        if self.config.get("main_zoomed"):
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass

    def _start_tray(self) -> None:
        self.tray.start()
        if self.tray.available:
            self.tray.update(self.engine.latest(), self._stale)

    def _show_initial_floating(self) -> None:
        if self.floating and not self._closing:
            self.floating.show()

    # -- callbacks -----------------------------------------------------
    @property
    def floating_visible(self) -> bool:
        return bool(self.floating and self.floating.visible)

    def show_main(self) -> None:
        if self._closing:
            return
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            if self._source_dialog is not None:
                self._source_dialog.focus()
        except tk.TclError:
            pass

    def show_sources(self) -> None:
        if self._closing:
            return
        self.show_main()
        snap = self.engine.latest()
        if self._source_dialog is not None:
            self._source_dialog.update_snapshot(snap)
            self._source_dialog.focus()
            return
        self._source_dialog = SourceDialog(self, self.root, self.theme, snap)
        self.root.after(
            100, lambda: dark_title_bar(self._source_dialog.win) if self._source_dialog else None
        )

    def on_source_dialog_closed(self, dialog: SourceDialog) -> None:
        if self._source_dialog is dialog:
            self._source_dialog = None

    def toggle_floating(self) -> None:
        if not self.floating:
            return
        self.floating.toggle()
        self.header.set_floating_visible(self.floating.visible)
        self.tray.refresh_menu()

    def on_floating_visibility(self, visible: bool) -> None:
        if self.header:
            self.header.set_floating_visible(visible)
        self.tray.refresh_menu()

    def post(self, func: Callable[[], None]) -> None:
        """Queue a callback for the Tk thread.

        Tray callbacks run on worker threads.  Calling Tk directly from those
        threads is not safe, so all UI work is funnelled through the main-loop
        tick.
        """
        if self._closing:
            return
        self._ui_queue.put(func)

    def _drain_ui_queue(self) -> None:
        while not self._closing:
            try:
                func = self._ui_queue.get_nowait()
            except queue.Empty:
                return
            try:
                func()
            except Exception:
                LOG.exception("Queued UI callback failed")

    # -- refresh -------------------------------------------------------
    def _tick(self) -> None:
        if self._closing:
            return
        self._drain_ui_queue()
        if self._closing:
            return
        try:
            snap = self.engine.latest()
            now = time.time()
            new_data = snap.seq != self._last_seq
            if new_data:
                self._last_seq = snap.seq
                self._stale = False
                self._history.append((snap.total_w, snap.cpu.power_w, snap.gpu.power_w))
            elif now - snap.timestamp > max(4.0, snap.refresh_s * 3.5):
                self._stale = True
            changed = new_data or self._stale != self._last_render_stale
            if changed:
                self._render(snap)
                self._last_render_stale = self._stale
        except Exception:
            LOG.exception("UI refresh failed")
            try:
                with open(
                    Path(tempfile.gettempdir()) / "NotebookPowerMonitor-ui-error.log",
                    "a",
                    encoding="utf-8",
                ) as handle:
                    traceback.print_exc(file=handle)
            except Exception:
                pass
        finally:
            if not self._closing:
                self._tick_job = self.root.after(300, self._tick)

    def _render(self, snap: Snapshot) -> None:
        stale = self._stale
        history = list(self._history)
        spark = [row[0] for row in history]
        self.header.update_status(snap, stale)
        self.header.set_floating_visible(bool(self.floating and self.floating.visible))
        self.total_card.update(snap, spark, stale)
        self.cpu_card.update(snap.cpu, stale)
        self.gpu_card.update(snap.gpu, stale)
        self.battery_card.update(snap.battery, stale)
        self.process_card.update(snap, stale)
        self.chart_card.update([] if stale else history, stale)
        self.footer.update(snap, stale)
        if self.floating:
            self.floating.update(snap, stale)
        now = time.time()
        if now - self._last_tray_update >= 1.5 or stale:
            self.tray.update(snap, stale)
            self._last_tray_update = now
        if self._source_dialog is not None:
            try:
                self._source_dialog.update_snapshot(snap)
            except tk.TclError:
                self._source_dialog = None

    # -- lifecycle -----------------------------------------------------
    def _save_window_state(self) -> None:
        try:
            if self.root.state() == "zoomed":
                self.config.set("main_zoomed", True)
            else:
                self.config.set("main_zoomed", False)
                geometry = self.root.geometry()
                if re.match(r"^\d+x\d+\+-?\d+\+-?\d+$", geometry):
                    self.config.set("main_geometry", geometry)
            self.config.set("floating_visible", bool(self.floating and self.floating.visible))
            self.config.save()
        except Exception:
            LOG.exception("Failed to save window state")

    def on_close(self) -> None:
        if self._closing:
            return
        self._save_window_state()
        if self.tray.available:
            try:
                self.root.withdraw()
            except tk.TclError:
                pass
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.notify(
                    "程序仍在任务栏托盘运行。双击图标或右键菜单可重新打开主界面。",
                    "电量哨兵",
                )
        else:
            self.quit_app()

    def quit_app(self) -> None:
        if self._closing:
            return
        self._closing = True
        LOG.info("Exiting")
        if self._tick_job:
            try:
                self.root.after_cancel(self._tick_job)
            except Exception:
                pass
        self._save_window_state()
        try:
            self.engine.stop()
        except Exception:
            LOG.exception("Engine stop failed")
        try:
            self.tray.stop()
        except Exception:
            LOG.exception("Tray stop failed")
        if self.floating:
            try:
                self.floating.destroy()
            except Exception:
                pass
        if self._source_dialog is not None:
            try:
                self._source_dialog.win.destroy()
            except Exception:
                pass
            self._source_dialog = None
        if self.single_instance is not None:
            try:
                self.single_instance.close()
            except Exception:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _report_callback_exception(self, exc, value, tb) -> None:
        LOG.exception("Unhandled Tk callback exception", exc_info=(exc, value, tb))
        try:
            messagebox.showerror(
                "电量哨兵遇到错误",
                f"{value}\n\n详细信息已写入日志：\n{Path.home()}",
                parent=self.root,
            )
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    demo = "--demo" in argv
    no_floating = "--no-floating" in argv
    setup_dpi_awareness()
    set_app_user_model_id()
    config = Config()
    if no_floating:
        config.set("floating_visible", False)
    instance = SingleInstance()
    if instance.already_running:
        instance.signal_existing()
        instance.close()
        return 0
    try:
        root = tk.Tk(className="NotebookPowerMonitor")
    except tk.TclError as exc:
        LOG.exception("Could not create Tk root")
        instance.close()
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                f"无法初始化图形界面：{exc}",
                "电量哨兵",
                0x10,
            )
        except Exception:
            pass
        return 1
    try:
        engine: MonitoringEngine | DemoEngine
        if demo:
            engine = DemoEngine(interval=1.0)
        else:
            engine = MonitoringEngine(interval=1.0)
        app = PowerMonitorApp(root, config, engine, demo=demo, single_instance=instance)
        if demo:
            LOG.info("Demo mode enabled")
        if "--sources" in argv:
            root.after(1200, app.show_sources)
        root.mainloop()
        instance.close()
        return 0
    except Exception:
        LOG.exception("Fatal application error")
        try:
            messagebox.showerror(
                "电量哨兵启动失败",
                f"程序启动失败，详情见日志：\n{app_data_dir() / 'monitor.log'}",
                parent=root,
            )
        except Exception:
            pass
        instance.close()
        try:
            root.destroy()
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
