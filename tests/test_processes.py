"""Process accounting bounds and Idle exclusion tests."""

from __future__ import annotations

import time
import unittest

from notebook_power_monitor.processes import ProcessSampler


class ProcessSafetyTests(unittest.TestCase):
    def test_background_cpu_is_bounded_and_excludes_idle(self) -> None:
        sampler = ProcessSampler()
        sampler.sample()
        time.sleep(1.15)
        info = sampler.sample()
        self.assertIsNotNone(info.active_pct)
        self.assertIsNotNone(info.background_pct)
        self.assertGreaterEqual(info.active_pct, 0.0)  # type: ignore[arg-type]
        self.assertLessEqual(info.active_pct, 100.0)  # type: ignore[arg-type]
        self.assertGreaterEqual(info.background_pct, 0.0)  # type: ignore[arg-type]
        self.assertLessEqual(info.background_pct, info.active_pct + 0.01)  # type: ignore[arg-type]
        for proc in info.top:
            self.assertLessEqual(proc.cpu_pct, 100.0)
            self.assertNotEqual(proc.name.lower(), "system idle process")
            self.assertNotEqual(proc.pid, 0)
        self.assertFalse(any(proc.name.lower() == "system idle process" for proc in info.top))


if __name__ == "__main__":
    unittest.main()
