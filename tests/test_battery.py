"""Battery and runtime-estimation tests."""

from __future__ import annotations

import time
import unittest

from notebook_power_monitor.battery import BatteryRaw, BatteryReader
from notebook_power_monitor.collector import MonitoringEngine


class BatteryTests(unittest.TestCase):
    def test_live_battery_is_sensor_backed(self) -> None:
        reader = BatteryReader()
        try:
            raw = reader.read()
        except Exception as exc:  # pragma: no cover - depends on CI hardware
            self.skipTest(f"Battery reader unavailable: {exc}")
        finally:
            reader.close()
        if not raw.present:
            self.skipTest("No battery on this machine")
        self.assertIsNotNone(raw.percent)
        self.assertGreater(raw.percent or 0, 0)
        if raw.remaining_wh is not None:
            self.assertGreater(raw.remaining_wh, 0)
        self.assertIn("WMI", raw.source + raw.detail)

    def test_runtime_estimate_uses_discharge_power(self) -> None:
        engine = MonitoringEngine()
        raw = BatteryRaw(
            present=True,
            ac_online=False,
            discharging=True,
            direction="discharging",
            remaining_wh=60.0,
            full_wh=80.0,
            power_w=30.0,
            percent=75.0,
            timestamp=time.time(),
        )
        runtime = None
        for _ in range(3):
            runtime, _to_full = engine._runtime_estimate(raw)
        self.assertIsNotNone(runtime)
        self.assertAlmostEqual((runtime or 0) / 3600.0, 2.0, places=2)

    def test_runtime_is_unavailable_without_rate(self) -> None:
        engine = MonitoringEngine()
        raw = BatteryRaw(
            present=True,
            ac_online=False,
            discharging=True,
            direction="discharging",
            remaining_wh=60.0,
            power_w=None,
            percent=75.0,
        )
        runtime, _to_full = engine._runtime_estimate(raw)
        self.assertIsNone(runtime)


if __name__ == "__main__":
    unittest.main()
