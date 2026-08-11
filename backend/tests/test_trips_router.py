from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")

from echogtfs.routers.trips import _build_trip_response_payload, _enrich_trips_with_entity_names, _filter_trips_with_stop_events


class TestTripsRouterHelpers(unittest.TestCase):
    def test_filter_trips_with_stop_events_suppresses_trips_without_stop_events(self):
        trips = [
            {"trip_id": "with-events", "stop_events": [{"stop_id": "s1"}]},
            {"trip_id": "without-events", "stop_events": []},
            {"trip_id": "without-events-alt", "stop_events": None},
        ]

        filtered = _filter_trips_with_stop_events(trips)

        self.assertEqual([trip["trip_id"] for trip in filtered], ["with-events"])

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

    def test_enrich_trips_with_entity_names_populates_vehicle_display_text(self):
        trips = [
            {
                "route_id": "route-1",
                "vehicle": {
                    "vehicle_label": "A 123",
                    "vehicle_license_plate": "B 456",
                    "vehicle_id": "vehicle-1",
                },
                "stop_events": [{"stop_id": "stop-3"}],
            }
        ]
        entity_names = {"route": {"route-1": "Route 1"}, "stop": {}}

        _enrich_trips_with_entity_names(trips, entity_names)

        self.assertEqual(trips[0]["vehicle_display_text"], "A 123")

    def test_build_trip_response_payload_preserves_assigned_vehicle(self):
        trip = SimpleNamespace(
            id=uuid4(),
            data_source_id=None,
            source="test",
            trip_id="trip-1",
            original_trip_id=None,
            scheduled_start_stop_id=None,
            scheduled_end_stop_id=None,
            scheduled_start_stop_name=None,
            scheduled_end_stop_name=None,
            scheduled_start_time=None,
            scheduled_end_time=None,
            start_time="10:00",
            start_date="20240101",
            route_id="route-1",
            route_name="Route 1",
            vehicle_display_text=None,
            schedule_relationship="SCHEDULED",
            assignment_type="DIRECT_BY_ID",
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            is_valid=True,
            stop_events=[],
            data_source_name=None,
            vehicle=SimpleNamespace(
                vehicle_label="A 123",
                vehicle_license_plate="B 456",
                vehicle_id="vehicle-1",
            ),
        )

        payload = _build_trip_response_payload(trip)

        self.assertEqual(payload["vehicle"]["vehicle_label"], "A 123")
        self.assertEqual(payload["vehicle"]["vehicle_id"], "vehicle-1")


if __name__ == "__main__":
    unittest.main()
