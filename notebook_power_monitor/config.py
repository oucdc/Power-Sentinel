"""Tiny JSON configuration store with atomic writes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .util import LOG, app_data_dir

DEFAULTS: dict[str, Any] = {
    "floating_visible": True,
    "floating_x": None,
    "floating_y": 18,
    "main_geometry": "",
    "main_zoomed": False,
    "close_to_tray": True,
}

CONFIG_PATH = app_data_dir() / "config.json"


class Config:
    def __init__(self) -> None:
        self._data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if key in DEFAULTS:
                        self._data[key] = value
        except FileNotFoundError:
            pass
        except Exception:
            LOG.exception("Failed to load config, using defaults")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        if key in DEFAULTS:
            self._data[key] = value

    def save(self) -> None:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = CONFIG_PATH.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, CONFIG_PATH)
        except Exception:
            LOG.exception("Failed to save config")

    def path(self) -> Path:
        return CONFIG_PATH
