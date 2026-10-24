"""GPU freshness / sleep-gating tests (no GPU required)."""

from __future__ import annotations

import time
import unittest

from notebook_power_monitor.collector import MonitoringEngine
from notebook_power_monitor.models import GpuNvmlReading, SourceStatus


class GpuSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = MonitoringEngine()
        self.nvml_ok = SourceStatus("nvml", "NVIDIA", "ok", "NVIDIA GPU", "")

    def test_gpu_is_unavailable_when_nvml_has_no_live_value(self) -> None:
        state = GpuNvmlReading(
            available=False,
            name="NVIDIA GeForce RTX 5080 Laptop GPU",
            error="GPU 功耗读数为 0（独显可能已休眠）",
            timestamp=time.time(),
        )
        info = self.engine._gpu_from_nvml(state, 0.2, self.nvml_ok)
        self.assertIsNone(info.power_w)
        self.assertFalse(info.nvml_ok)
        self.assertIn("休眠", info.reason)

    def test_stale_nvml_is_not_shown(self) -> None:
        state = GpuNvmlReading(
            available=True,
            name="NVIDIA GeForce RTX 5080 Laptop GPU",
            power_w=40.0,
            temp_c=50.0,
            timestamp=time.time() - 6,
        )
        info = self.engine._gpu_from_nvml(state, 6.0, self.nvml_ok)
        self.assertIsNone(info.power_w)
        self.assertIn("无响应", info.reason)

    def test_live_nvml_is_used(self) -> None:
        state = GpuNvmlReading(
            available=True,
            name="NVIDIA GeForce RTX 5080 Laptop GPU",
            power_w=40.5,
            temp_c=51.0,
            util_pct=12.0,
            timestamp=time.time(),
        )
        info = self.engine._gpu_from_nvml(state, 0.2, self.nvml_ok)
        self.assertAlmostEqual(info.power_w, 40.5)  # type: ignore[arg-type]
        self.assertIn("NVML", info.source)
        self.assertTrue(info.nvml_ok)


if __name__ == "__main__":
    unittest.main()
