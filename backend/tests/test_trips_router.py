from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")

from echogtfs.routers.trips import _enrich_trips_with_entity_names


class TestTripsRouterHelpers(unittest.TestCase):
    def test_enrich_trips_with_entity_names_populates_scheduled_stop_names(self):
        trips = [
            {
                "route_id": "route-1",
                "scheduled_start_stop_id": "stop-1",
                "scheduled_end_stop_id": "stop-2",
                "stop_events": [{"stop_id": "stop-3", "is_valid": False}],
            }
        ]
        entity_names = {
            "route": {"route-1": "Route 1"},
            "stop": {"stop-1": "Start Stop", "stop-2": "End Stop"},
        }

        _enrich_trips_with_entity_names(trips, entity_names)

        self.assertEqual(trips[0]["route_name"], "Route 1")
        self.assertEqual(trips[0]["scheduled_start_stop_name"], "Start Stop")
        self.assertEqual(trips[0]["scheduled_end_stop_name"], "End Stop")
        self.assertFalse(trips[0]["is_valid"])


if __name__ == "__main__":
    unittest.main()
