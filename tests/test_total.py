"""Total-power selection tests: battery on DC, CPU+GPU on AC."""

from __future__ import annotations

import unittest

from notebook_power_monitor.battery import BatteryRaw
from notebook_power_monitor.collector import MonitoringEngine


class TotalSelectionTests(unittest.TestCase):
    def test_dc_uses_measured_battery_discharge(self) -> None:
        raw = BatteryRaw(
            present=True,
            ac_online=False,
            discharging=True,
            direction="discharging",
            power_w=45.0,
        )
        total, source, _label, _reason, kind = MonitoringEngine._select_total(raw, 32.0, 18.0, 99.0)
        self.assertAlmostEqual(total, 45.0)  # type: ignore[arg-type]
        self.assertEqual(source, "电池放电实测")
        self.assertEqual(kind, "battery")

    def test_ac_uses_cpu_plus_gpu_and_labels_it_computed(self) -> None:
        raw = BatteryRaw(present=True, ac_online=True, charging=True)
        total, source, label, reason, kind = MonitoringEngine._select_total(raw, 60.0, 40.0, 0.0)
        self.assertAlmostEqual(total, 100.0)  # type: ignore[arg-type]
        self.assertEqual(source, "CPU+GPU 合计")
        self.assertEqual(label, "CPU+GPU 双烤合计")
        self.assertEqual(kind, "computed")
        self.assertIn("不是墙插", reason)

    def test_ac_falls_back_to_power_meter_when_gpu_is_unavailable(self) -> None:
        raw = BatteryRaw(present=True, ac_online=True, charging=True)
        total, source, _label, _reason, kind = MonitoringEngine._select_total(raw, 60.0, None, 75.0)
        self.assertAlmostEqual(total, 75.0)  # type: ignore[arg-type]
        self.assertEqual(source, "Windows Power Meter")
        self.assertEqual(kind, "meter")

    def test_ac_without_components_or_meter_is_unavailable(self) -> None:
        raw = BatteryRaw(present=True, ac_online=True, charging=True)
        total, source, _label, reason, kind = MonitoringEngine._select_total(raw, 60.0, None, None)
        self.assertIsNone(total)
        self.assertEqual(source, "")
        self.assertEqual(kind, "")
        self.assertIn("无法计算双烤合计", reason)

    def test_dc_does_not_fall_back_to_cpu_plus_gpu(self) -> None:
        raw = BatteryRaw(
            present=True,
            ac_online=False,
            discharging=True,
            direction="discharging",
            power_w=None,
        )
        total, _source, _label, reason, kind = MonitoringEngine._select_total(raw, 60.0, 40.0, None)
        self.assertIsNone(total)
        self.assertEqual(kind, "")
        self.assertIn("未报告", reason)


if __name__ == "__main__":
    unittest.main()
