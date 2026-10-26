# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-10-26

### Added

- AC total power now shows the explicit CPU+GPU dual-load sum (“双烤功耗合计”), labelled as a
  calculated value.
- Total power provenance is stored in `Snapshot.total_kind` and rendered in the dashboard, floating
  bar, tray tooltip and diagnostics.

### Changed

- On battery, total power continues to use measured battery discharge.
- If either CPU or GPU power is unavailable on AC, the app falls back to a real Windows Power Meter
  reading, otherwise the total is explicitly unavailable.
- README, architecture and contribution docs now describe the computed AC total and its limits.

## [1.0.2] - 2026-10-24

### Changed

- Removed the HWiNFO shared-memory integration entirely.
- CPU power now comes only from Windows RAPL.
- GPU power and temperature now come only from NVIDIA NVML.
- Total system power now comes only from Windows Power Meter or measured battery discharge.
- CPU temperature is no longer displayed; native Windows APIs do not provide a trustworthy package temperature.
- Renamed the Python package to `notebook_power_monitor` and moved runtime assets inside the package.
- Reorganised the repository for open-source distribution: `pyproject.toml`, CI, issue/PR templates,
  contributing/security/conduct documents, and English/Chinese READMEs.

### Removed

- HWiNFO process detection, shared-memory parser, executable discovery and launch helpers.
- HWiNFO settings and diagnostics from the data-source dialog.

## [1.0.1] - 2026-10-24

### Added

- Support for localised HWiNFO sensor labels, including `CPU 封装功率`, `GPU 功率` and `CPU 封装`.
- Protection against selecting “distance to TjMAX” as a CPU temperature.

### Fixed

- HWiNFO sensor selection when the HWiNFO UI language is Chinese.

## [1.0.0] - 2026-10-24

### Added

- Initial Windows release.
- Native CPU RAPL and NVIDIA NVML monitoring.
- Battery runtime estimate from remaining capacity and measured discharge power.
- Background process accounting with `System Idle Process` and foreground process excluded.
- Main dashboard, floating bar, tray icon and single-instance activation.
