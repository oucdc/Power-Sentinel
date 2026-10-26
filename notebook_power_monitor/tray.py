"""Taskbar notification-area integration.

pystray is optional at runtime: if it is not installed (or fails to start), the
dashboard still runs, and closing the main window simply exits instead of
hiding to the tray.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .models import Snapshot
from .util import LOG, fmt_power, fmt_short_runtime

try:  # optional dependency, bundled in the frozen build
    import pystray
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - only on systems without the extras
    pystray = None  # type: ignore[assignment]
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]


def _fallback_image():
    if Image is None or ImageDraw is None:
        return None
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (2, 2, 62, 62), radius=16, fill=(12, 27, 40, 255), outline=(32, 80, 101, 255), width=2
    )
    draw.polygon(
        [(36, 8), (18, 36), (30, 36), (25, 56), (47, 27), (34, 27)],
        fill=(77, 216, 255, 255),
    )
    return img


def _load_image(icon_path: Path | None):
    if icon_path and Path(icon_path).is_file() and Image is not None:
        try:
            with Image.open(icon_path) as image:
                return image.convert("RGBA").copy()
        except Exception:
            LOG.exception("Failed to load tray icon")
    return _fallback_image()


class TrayController:
    def __init__(self, app: Any, icon_path: Path | None) -> None:
        self.app = app
        self.icon_path = icon_path
        self.icon = None
        self.available = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        if pystray is None or Image is None:
            LOG.info("pystray/Pillow unavailable; tray disabled")
            return False
        # pystray 0.19 calls ChangeWindowMessageFilterEx with an errchecker.
        # On some hardened Windows builds this call returns ERROR_ACCESS_DENIED
        # even though the notification icon itself works fine.  The message
        # filter is only needed to catch Explorer restarts, so ignore that
        # specific failure instead of losing the whole tray icon.
        try:
            from pystray._util import win32 as _pwin32

            _original_filter = _pwin32.ChangeWindowMessageFilterEx

            def _safe_filter(hwnd, message, action, ptr=None):
                try:
                    return _original_filter(hwnd, message, action, ptr)
                except Exception:
                    return 0

            _pwin32.ChangeWindowMessageFilterEx = _safe_filter
        except Exception:
            LOG.debug("Could not patch pystray message filter", exc_info=True)
        image = _load_image(self.icon_path)
        if image is None:
            return False
        try:
            menu = pystray.Menu(
                pystray.MenuItem("显示主窗口", self._show_main, default=True),
                pystray.MenuItem(
                    "顶部悬浮条",
                    self._toggle_floating,
                    checked=lambda _item: bool(self.app.floating_visible),
                ),
                pystray.MenuItem("数据源与诊断", self._sources),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出电量哨兵", self._quit),
            )
            self.icon = pystray.Icon(
                "NotebookPowerMonitor",
                image,
                "电量哨兵",
                menu,
            )
            self._thread = threading.Thread(target=self._run, name="Tray", daemon=True)
            self._thread.start()
            self.available = True
            LOG.info("Tray icon started")
            return True
        except Exception:
            LOG.exception("Failed to create tray icon")
            self.available = False
            return False

    def _run(self) -> None:
        try:
            if self.icon is not None:
                self.icon.run()
        except Exception:
            LOG.exception("Tray icon loop failed")
            self.available = False

    def _show_main(self, _icon=None, _item=None) -> None:
        self.app.post(self.app.show_main)

    def _toggle_floating(self, _icon=None, _item=None) -> None:
        self.app.post(self.app.toggle_floating)

    def _sources(self, _icon=None, _item=None) -> None:
        self.app.post(self.app.show_sources)

    def _quit(self, _icon=None, _item=None) -> None:
        self.app.post(self.app.quit_app)

    def refresh_menu(self) -> None:
        if self.icon is not None:
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def notify(self, message: str, title: str = "电量哨兵") -> None:
        if self.icon is not None:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def update(self, snap: Snapshot, stale: bool = False) -> None:
        if self.icon is None:
            return
        if stale:
            title = "电量哨兵 · 采集中断"
        elif snap.demo:
            title = "电量哨兵 · 演示模式"
        else:
            total = f"{fmt_power(snap.total_w, 1)} W" if snap.total_w is not None else "—"
            total_caption = "双烤" if snap.total_kind == "computed" else "整机"
            cpu = f"{fmt_power(snap.cpu.power_w, 1)} W" if snap.cpu.power_w is not None else "—"
            gpu = f"{fmt_power(snap.gpu.power_w, 1)} W" if snap.gpu.power_w is not None else "—"
            percent = f"{snap.battery.percent:.0f}%" if snap.battery.percent is not None else "—"
            runtime = "—"
            if snap.battery.direction == "discharging":
                runtime = fmt_short_runtime(snap.battery.runtime_seconds)
            elif snap.battery.charging:
                runtime = "充电"
            elif snap.battery.ac_online:
                runtime = "AC"
            title = (
                f"{total_caption} {total} | CPU {cpu} | GPU {gpu}\n电量 {percent} | 续航 {runtime}"
            )
        try:
            self.icon.title = title[:127]
        except Exception:
            pass

    def stop(self) -> None:
        self._stop.set()
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.available = False
