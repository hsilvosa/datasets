from __future__ import annotations

import unittest
from pathlib import Path

from entsoe_transparency.config import Config
from entsoe_transparency.tasks import build_tasks

PROJECT = Path(__file__).resolve().parents[1]


class ConfigTaskTests(unittest.TestCase):
    def test_sample_has_six_tasks(self):
        config = Config.load(PROJECT / "configs" / "sample.json")
        tasks = build_tasks(config)
        self.assertEqual(len(tasks), 6)
        self.assertEqual({task.zone.key for task in tasks}, {"ES", "FR", "DE_LU"})
        self.assertEqual(
            {task.dataset for task in tasks}, {"day_ahead_prices", "actual_load"}
        )

    def test_historical_german_zone_does_not_overlap_current_zone(self):
        config = Config.load(PROJECT / "configs" / "default.json")
        tasks = build_tasks(config)
        historical = [task for task in tasks if task.zone.key == "DE_AT_LU"]
        current = [task for task in tasks if task.zone.key == "DE_LU"]
        self.assertTrue(historical)
        self.assertTrue(current)
        self.assertLessEqual(max(task.end for task in historical), min(task.start for task in current))


if __name__ == "__main__":
    unittest.main()
