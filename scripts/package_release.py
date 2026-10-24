"""Assemble the final release folder and zip archive."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "dist" / "电量哨兵"
DOCS = ROOT / "docs"
RELEASE = ROOT / "release"
ZIP = RELEASE / "电量哨兵-v1.0.2.zip"

if not (APP / "电量哨兵.exe").is_file():
    raise SystemExit(f"missing app: {APP / '电量哨兵.exe'}")
for name in ("README.md", "README.zh-CN.md", "LICENSE", "CHANGELOG.md", "SECURITY.md"):
    source = ROOT / name
    if source.is_file():
        shutil.copy2(source, APP / name)
if DOCS.is_dir():
    target = APP / "docs"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(DOCS, target)
# Never ship test logs/configuration.
data = APP / "NotebookPowerMonitor-data"
if data.exists():
    shutil.rmtree(data, ignore_errors=True)
RELEASE.mkdir(parents=True, exist_ok=True)
if ZIP.exists():
    ZIP.unlink()
with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(APP.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(ROOT / "dist"))
print(f"release folder: {APP}")
print(f"zip: {ZIP} ({ZIP.stat().st_size / 1024 / 1024:.1f} MiB)")
