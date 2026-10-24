# Architecture

Notebook Power Monitor is a small, sensor-driven Tk application. It deliberately has no network
layer, database or background service.

## Data flow

```text
Windows RAPL (PDH) ─┐
NVIDIA NVML ────────┼─► MonitoringEngine ─► Snapshot ─► Tk UI / tray / floating bar
WMI + ACPI battery ─┤        (1 Hz)
Win32 process times ┘
```

- `MonitoringEngine` runs on one collector thread and builds an immutable `Snapshot` once per second.
- `GpuSampler` owns NVML on a separate thread because some driver calls can block while the dGPU
  sleeps. The collector reads only its latest sample and its age.
- The UI renders snapshots on the Tk main thread. Tray callbacks are marshalled through a
  `queue.SimpleQueue`; Tk is never called from a worker thread.

## Source modules

| Module | Responsibility |
|---|---|
| `rapl.py` | PDH counters for `Energy Meter(RAPL_Package0_PKG)` and Windows Power Meter |
| `gpu.py` | NVML init, polling, freshness, sleep/error handling |
| `battery.py` | ACPI static battery information + WMI dynamic status |
| `processes.py` | Toolhelp32 process enumeration and CPU-time deltas |
| `collector.py` | Source merging, total-power selection, runtime estimates, snapshots |
| `models.py` | Dataclasses shared by the collector and UI |
| `dialogs.py` | Data-source health and copyable diagnostics |
| `ui_cards.py`, `floating.py`, `tray.py` | Presentation |
| `main.py` | DPI awareness, single instance, windows, shutdown |
| `util.py` | Logging, data-directory fallback, formatting, asset lookup |

## Invariants

1. **No fabricated power.** Total system power is only Windows Power Meter or measured battery
   discharge. CPU+GPU is never presented as total power.
2. **No stale GPU data.** A GPU sample older than 3.5 seconds, an NVML error, or a zero power reading
   makes the GPU card unavailable.
3. **Background CPU is bounded.** PID 0 / `System Idle Process` and the foreground process are
   excluded; process percentages are normalised by logical CPU count; the background total cannot
   exceed the system's active CPU.
4. **Unknown is visible.** Missing sensors produce an explicit unavailable state with a reason, not a
   placeholder number.
5. **No elevation requirement.** The app runs as the current user. HWiNFO integration was removed in
   1.0.2 and the app does not depend on external monitoring tools.

## Data directory

The app probes these locations and uses the first writable one:

1. `%APPDATA%\NotebookPowerMonitor\`
2. `%LOCALAPPDATA%\NotebookPowerMonitor\`
3. `<exe-directory>\NotebookPowerMonitor-data\`
4. A temporary fallback

`monitor.log` rotates at 768 KB and keeps three backups. `config.json` stores window geometry and
floating-bar preferences only.

## Threading and shutdown

The collector and GPU sampler are daemon threads. `MonitoringEngine.stop()` signals the collector,
joins it, then closes PDH, WMI and NVML handles. Tk shutdown is guarded by `_closing` so queued
callbacks cannot touch destroyed widgets.

## Packaging

The release is a PyInstaller **onedir** build. One-file mode was rejected because some Windows
security policies deny temporary-directory execution. Runtime assets live inside the
`notebook_power_monitor` package and are copied to `_MEIPASS/assets` in the frozen build.

See [releasing.md](releasing.md) for the build and release checklist.
