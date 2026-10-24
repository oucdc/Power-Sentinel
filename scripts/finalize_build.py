"""Rename the built onedir folder and EXE to the Chinese product name.

PowerShell/PyInstaller can mangle non-ASCII --name values when the build is
launched through different code pages; doing the rename in Python keeps the
filesystem names correct.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
src_dir = DIST / "NotebookPowerMonitor"
src_exe = src_dir / "NotebookPowerMonitor.exe"
dst_dir = DIST / "电量哨兵"
dst_exe = dst_dir / "电量哨兵.exe"
if not src_exe.is_file():
    raise SystemExit(f"missing {src_exe}")
if dst_dir.exists():
    shutil.rmtree(dst_dir, ignore_errors=True)
src_dir.rename(dst_dir)
(dst_dir / "NotebookPowerMonitor.exe").rename(dst_exe)
print(dst_exe)
