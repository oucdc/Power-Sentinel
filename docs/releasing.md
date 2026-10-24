# Releasing

This project follows [Semantic Versioning](https://semver.org/).

## Version bump

Update all of these together:

1. `notebook_power_monitor/__init__.py` — `__version__`
2. `packaging/windows/version_info.txt` — `filevers`, `prodvers`, `FileVersion`, `ProductVersion`
3. `CHANGELOG.md` — add a dated section
4. `scripts/package_release.py` — ZIP filename
5. Any version statement in the READMEs if present

The Python package version is read from `notebook_power_monitor.__version__` by `pyproject.toml`.

## Pre-flight checks

```powershell
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m notebook_power_monitor --demo
```

Start the real app and verify:

- CPU RAPL power and GPU NVML power/temperature.
- Battery percentage and charging/discharging state.
- Floating bar, tray menu and single-instance activation.
- GPU card becomes unavailable after the dGPU sleeps; no stale values remain.
- Total power is unavailable on AC when Windows Power Meter has no reading.

## Build

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build.ps1
python .\scripts\package_release.py
```

The build script runs the tests, regenerates the icon, creates an ASCII-named onedir build, then
renames the directory and EXE to `电量哨兵`. `package_release.py` removes the runtime data directory,
copies documentation, and writes `release\电量哨兵-vX.Y.Z.zip`.

## Verify the artifact

1. Extract the ZIP into a clean directory.
2. Confirm the folder contains `电量哨兵.exe`, `_internal\`, `README.md`, `README.zh-CN.md`,
   `CHANGELOG.md`, `LICENSE` and `docs\`.
3. Launch from the extracted folder, close to tray, and launch again to test single-instance restore.
4. Record the ZIP SHA-256:

```powershell
Get-FileHash .\release\电量哨兵-vX.Y.Z.zip -Algorithm SHA256
```

## GitHub release

- Tag: `vX.Y.Z` (for example `v1.0.2`).
- Title: `电量哨兵 vX.Y.Z`.
- Attach only the release ZIP, not `build/`, `dist/` or logs.
- Paste the relevant `CHANGELOG.md` section into the release notes.
- Mention whether the release is source-only or includes the Windows binary.
- Upload the SHA-256 in the release body.

Do not commit build artifacts; `.gitignore` excludes `build/`, `dist/`, `release/` and runtime data.
