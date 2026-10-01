from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _service_test_bootstrap  # noqa: F401

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from echogtfs.services.realtimeprocessing.stop_event_propagation_service import (
    StopEventPropagationService,
)


class TestOccurrenceAwareMissingStopPropagation(unittest.TestCase):
    def setUp(self):
        self.service = StopEventPropagationService()
        self.base_time = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)

    def _nominal(self, stop_id: str, sequence: int):
        planned_time = self.base_time + timedelta(minutes=sequence)
        return SimpleNamespace(
            stop_id=stop_id,
            stop_sequence=sequence,
            arrival_time=planned_time,
            departure_time=planned_time,
        )

    def _event(self, stop_id: str, minute: int, relationship: str = "SCHEDULED"):
        event_time = self.base_time + timedelta(minutes=minute)
        return {
            "stop_id": stop_id,
            "arrival_time": event_time,
            "departure_time": event_time,
            "scheduled_departure_time": event_time,
            "schedule_relationship": relationship,
            "is_implied_schedule_relationship": False,
        }

    def test_missing_duplicate_occurrence_is_synthesized_as_skipped(self):
        nominal = [
            self._nominal("s1", 1),
            self._nominal("s2", 2),
            self._nominal("s2", 3),
            self._nominal("s3", 4),
        ]
        realtime = [
            self._event("s1", 1),
            self._event("s2", 2),
            self._event("s3", 4),
        ]

        propagated = self.service._propagate_trip_update_stop_events(
            realtime,
            nominal,
            treat_unexpected_stop_as_added_stop=True,
            treat_missing_stop_as_canceled_stop=True,
            is_complete_stop_sequence=True,
        )

        s2_events = [event for event in propagated if event["stop_id"] == "s2"]
        self.assertEqual(len(s2_events), 2)
        self.assertEqual(
            sorted(event["schedule_relationship"] for event in s2_events),
            ["SCHEDULED", "SKIPPED"],
        )
        implied_skipped = next(
            event for event in s2_events if event["schedule_relationship"] == "SKIPPED"
        )
        self.assertTrue(implied_skipped["is_implied_schedule_relationship"])
        self.assertEqual(implied_skipped["stop_sequence"], "3")

    def test_reordered_stop_becomes_added_and_nominal_occurrence_becomes_skipped(self):
        nominal = [
            self._nominal("s1", 1),
            self._nominal("s2", 2),
            self._nominal("s3", 3),
            self._nominal("s4", 4),
        ]
        realtime = [
            self._event("s1", 1),
            self._event("s3", 3),
            self._event("s2", 4),
            self._event("s4", 5),
        ]

        propagated = self.service._propagate_trip_update_stop_events(
            realtime,
            nominal,
            treat_unexpected_stop_as_added_stop=True,
            treat_missing_stop_as_canceled_stop=True,
            is_complete_stop_sequence=True,
        )

        s2_events = [event for event in propagated if event["stop_id"] == "s2"]
        self.assertEqual(len(s2_events), 2)
        self.assertEqual(
            {event["schedule_relationship"] for event in s2_events},
            {"ADDED", "SKIPPED"},
        )
        self.assertTrue(
            all(event["is_implied_schedule_relationship"] for event in s2_events)
        )

    def test_missing_duplicate_occurrence_is_synthesized_as_no_data_when_not_canceled(self):
        nominal = [
            self._nominal("s1", 1),
            self._nominal("s2", 2),
            self._nominal("s2", 3),
            self._nominal("s3", 4),
        ]
        realtime = [
            self._event("s1", 1),
            self._event("s2", 2),
            self._event("s3", 4),
        ]

        propagated = self.service._propagate_trip_update_stop_events(
            realtime,
            nominal,
            treat_unexpected_stop_as_added_stop=True,
            treat_missing_stop_as_canceled_stop=False,
            is_complete_stop_sequence=True,
        )

        s2_events = [event for event in propagated if event["stop_id"] == "s2"]
        self.assertEqual(len(s2_events), 2)
        no_data = next(
            event for event in s2_events if event["schedule_relationship"] == "NO_DATA"
        )
        self.assertFalse(no_data["is_implied_schedule_relationship"])
        self.assertEqual(no_data["stop_sequence"], "3")

    def test_missing_detection_preserves_station_level_semantics_when_added_detection_is_disabled(self):
        nominal = [
            self._nominal("de:1:2:4", 1),
            self._nominal("de:1:2:5", 2),
        ]
        realtime = [
            self._event("de:1:2:3", 1),
        ]

        propagated = self.service._propagate_trip_update_stop_events(
            realtime,
            nominal,
            treat_unexpected_stop_as_added_stop=False,
            treat_missing_stop_as_canceled_stop=True,
            is_complete_stop_sequence=True,
        )

        self.assertEqual(
            [event["stop_id"] for event in propagated],
            ["de:1:2:3"],
        )

    def test_alignment_reports_both_realtime_and_nominal_occurrences(self):
        nominal = [
            self._nominal("s1", 1),
            self._nominal("s2", 2),
            self._nominal("s3", 3),
        ]
        realtime = [
            self._event("s1", 1),
            self._event("sx", 2),
            self._event("s3", 3),
        ]

        matched_realtime, matched_nominal = self.service._align_stop_occurrences(
            realtime,
            nominal,
        )

        self.assertEqual(matched_realtime, {0, 2})
        self.assertEqual(matched_nominal, {0, 2})


if __name__ == "__main__":
    unittest.main()
