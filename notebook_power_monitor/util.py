"""Small helpers: formatting, paths, logging and Win32 resource access."""

from __future__ import annotations

import logging
import logging.handlers
import math
import os
import sys
import tempfile
import time
from pathlib import Path

from . import __app_name__, __version__

APP_ID = "NotebookPowerMonitor"
APP_NAME = __app_name__
APP_VERSION = __version__
_APP_DIR: Path | None = None


def _writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def app_data_dir() -> Path:
    """Return a writable per-user data directory.

    The installed/frozen executable can be subjected to third-party security
    policies that deny writes to Roaming AppData while still allowing writes
    next to the EXE.  Probe a few locations instead of silently losing the
    configuration and log.
    """
    global _APP_DIR
    if _APP_DIR is not None:
        return _APP_DIR
    candidates: list[Path] = []
    roaming = os.environ.get("APPDATA")
    local = os.environ.get("LOCALAPPDATA")
    if roaming:
        candidates.append(Path(roaming) / APP_ID)
    if local:
        candidates.append(Path(local) / APP_ID)
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "NotebookPowerMonitor-data")
    except Exception:
        pass
    candidates.append(Path(tempfile.gettempdir()) / APP_ID)
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if _writable_dir(candidate):
            _APP_DIR = candidate
            return candidate
    # Let the caller's own error handling deal with the unwritable path.
    _APP_DIR = candidates[0] if candidates else Path.home() / ("." + APP_ID)
    return _APP_DIR


def resource_path(relative: str) -> Path:
    """Resolve a packaged asset both in source and in a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).resolve().parent / relative


def setup_logging() -> logging.Logger:
    logger = logging.getLogger(APP_ID)
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s")
    # In a console build (and in normal source runs) expose tracebacks on
    # stderr as well, which makes a silently failing UI tick diagnosable.
    if sys.stderr is not None:
        try:
            stream = logging.StreamHandler(sys.stderr)
            stream.setFormatter(formatter)
            logger.addHandler(stream)
        except Exception:
            pass
    path: Path | None = None
    try:
        path = app_data_dir() / "monitor.log"
        handler = None
        last_error: Exception | None = None
        for _attempt in range(4):
            try:
                handler = logging.handlers.RotatingFileHandler(
                    path, maxBytes=768 * 1024, backupCount=2, encoding="utf-8"
                )
                break
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.15)
        if handler is None:
            raise last_error or PermissionError(str(path))
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.info("Logging to %s", path)
    except Exception:
        fallback = Path(tempfile.gettempdir()) / "NotebookPowerMonitor-monitor.log"
        try:
            handler = logging.handlers.RotatingFileHandler(
                fallback, maxBytes=512 * 1024, backupCount=1, encoding="utf-8"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.exception("Primary log path failed (%s); using %s", path, fallback)
        except Exception:
            logger.addHandler(logging.NullHandler())
            logger.exception("Could not create any log file")
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())
    return logger


LOG = setup_logging()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def is_number(value: object) -> bool:
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


def fmt_power(value: float | None, digits: int = 1, dash: str = "—") -> str:
    if not is_number(value):
        return dash
    v = float(value)  # type: ignore[arg-type]
    if v < 0:
        return dash
    return f"{v:.{digits}f}"


def fmt_pct(value: float | None, digits: int = 1, dash: str = "—") -> str:
    if not is_number(value):
        return dash
    return f"{clamp(float(value), 0.0, 100.0):.{digits}f}%"


def fmt_wh(value: float | None) -> str:
    if not is_number(value):
        return "—"
    return f"{float(value) / 1000.0:.1f} Wh"


def fmt_runtime(seconds: float | None) -> str:
    if not is_number(seconds):
        return "—"
    s = max(0.0, float(seconds))
    total_min = int(round(s / 60.0))
    if total_min < 1:
        return "不足 1 分钟"
    if total_min < 60:
        return f"{total_min} 分钟"
    hours, minutes = divmod(total_min, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days} 天 {hours} 小时"
    return f"{hours} 小时 {minutes:02d} 分"


def fmt_short_runtime(seconds: float | None) -> str:
    if not is_number(seconds):
        return "—"
    s = max(0.0, float(seconds))
    total_min = int(round(s / 60.0))
    if total_min < 1:
        return "<1 分"
    hours, minutes = divmod(total_min, 60)
    if hours >= 24:
        return f"{hours // 24}天{hours % 24}时"
    return f"{hours}:{minutes:02d}"


def fmt_age(seconds: float | None) -> str:
    if not is_number(seconds):
        return "—"
    s = max(0.0, float(seconds))
    if s < 1.5:
        return "刚刚"
    if s < 60:
        return f"{int(s)} 秒前"
    return f"{int(s // 60)} 分钟前"


def fmt_clock(ts: float | None = None) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts or time.time()))


def short_name(name: str, limit: int = 26) -> str:
    clean = (name or "").strip()
    if clean.lower().endswith(".exe"):
        clean = clean[:-4]
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "…"


def format_hw_path(path: str) -> str:
    if not path:
        return "未设置"
    return path


def resource_icon_path() -> Path | None:
    for rel in ("assets/app.ico", "assets/icon.ico"):
        p = resource_path(rel)
        if p.is_file():
            return p
    return None


def open_path(path: str | Path) -> None:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        LOG.exception("Could not open path: %s", path)
