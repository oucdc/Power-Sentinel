# Contributing

Thanks for helping improve Notebook Power Monitor.

## Before you start

- Search existing issues and pull requests first.
- For a substantial feature, open an issue to discuss the scope before writing code.
- Report security issues privately as described in [SECURITY.md](SECURITY.md), not in a public issue.

## Development setup

Requirements: Windows 10/11 and 64-bit Python 3.10+.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the app:

```powershell
python -m notebook_power_monitor
```

Run tests and lint:

```powershell
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
```

Hardware-dependent tests skip automatically when the machine has no battery. Tests must not require
NVIDIA hardware or a graphical desktop.

## Coding guidelines

- Keep the UI in Simplified Chinese and code/comments in English.
- Use type hints for new public functions and dataclasses.
- Prefer native Windows APIs and existing data models; do not add a CPU+GPU sum as a substitute for
  total system power.
- Preserve the “unknown is unavailable” rule: never display a fabricated or stale sensor value.
- Keep new dependencies minimal and justify them in the pull request.
- Follow the existing module boundaries: acquisition in `battery.py` / `gpu.py` / `rapl.py`, merging in
  `collector.py`, presentation in `ui_*.py`, lifecycle in `main.py`.

## Commits and pull requests

- Use clear, imperative commit subjects (Conventional Commits are welcome, for example
  `fix: hide stale GPU values on resume`).
- Keep each PR focused. Separate refactors from behaviour changes.
- Add or update tests for behaviour changes.
- Include a screenshot for visible UI changes.
- Confirm the PR checklist and describe how the change was tested.
- Do not commit `build/`, `dist/`, `release/`, logs, local configuration or generated binaries.

## Building a release

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build.ps1
python .\scripts\package_release.py
```

See [docs/releasing.md](docs/releasing.md) for the full release checklist.

## License

By contributing, you agree that your contribution is licensed under the MIT License.
