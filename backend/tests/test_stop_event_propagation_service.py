from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _service_test_bootstrap  # noqa: F401

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from echogtfs.enum.gtfsrt import AssignmentType
from echogtfs.enum.system import IncorrectStopIdHandling, InvalidReferencePolicy
from _realtimeprocessing_test_support import _SystemRepositoryStub, _RealtimeRepositoryStub, _GtfsRepositoryStub, make_processor
from echogtfs.services.realtimeprocessing.stop_event_propagation_service import StopEventPropagationService

class TestStopEventPropagationService(unittest.TestCase):
    def setUp(self):
        self.datasource = StopEventPropagationService()

    def test_propagate_trip_update_stop_events_matches_global_ids_at_level_3(self):
        same_time = datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)
        stop_events = [
            {
                "stop_id": "de:1:2:3",
                "stop_sequence": "10",
                "departure_time": same_time,
                "schedule_relationship": "SCHEDULED",
            }
        ]
        nominal_stop_times = [
            SimpleNamespace(stop_id="de:1:2:4", stop_sequence=1, arrival_time=None, departure_time=same_time),
        ]

        propagated = self.datasource._propagate_trip_update_stop_events(
            stop_events,
            nominal_stop_times,
            treat_unexpected_stop_as_added_stop=False,
            treat_missing_stop_as_canceled_stop=False,
            is_complete_stop_sequence=True,
        )

        self.assertEqual(len(propagated), 1)
        self.assertIn("de:1:2:3", [event["stop_id"] for event in propagated])
    def test_propagate_trip_update_stop_events_sorts_station_level_leftovers_like_added(self):
        base_time = datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)
        stop_events = [
            {
                "stop_id": "de:1:2:3",
                "departure_time": base_time.replace(minute=5),
                "schedule_relationship": "SCHEDULED",
            }
        ]
        nominal_stop_times = [
            SimpleNamespace(
                stop_id="de:1:2:4",
                stop_sequence=1,
                arrival_time=None,
                departure_time=base_time.replace(minute=10),
            ),
            SimpleNamespace(
                stop_id="de:1:2:5",
                stop_sequence=2,
                arrival_time=None,
                departure_time=base_time.replace(minute=20),
            ),
        ]

        propagated = self.datasource._propagate_trip_update_stop_events(
            stop_events,
            nominal_stop_times,
            treat_unexpected_stop_as_added_stop=False,
            treat_missing_stop_as_canceled_stop=False,
            is_complete_stop_sequence=True,
        )

        self.assertEqual(
            [event["stop_id"] for event in propagated],
            ["de:1:2:3"],
        )
    def test_propagate_trip_update_stop_events_preserves_existing_stop_sequences(self):
        same_time = datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)
        stop_events = [
            {
                "stop_id": "s2",
                "stop_sequence": "20",
                "departure_time": same_time,
                "schedule_relationship": "SCHEDULED",
            },
            {
                "stop_id": "s1",
                "stop_sequence": "10",
                "departure_time": same_time,
                "schedule_relationship": "SCHEDULED",
            },
        ]
        nominal_stop_times = [
            SimpleNamespace(stop_id="s1", stop_sequence=1, arrival_time=None, departure_time=same_time),
            SimpleNamespace(stop_id="s2", stop_sequence=2, arrival_time=None, departure_time=same_time),
        ]

        propagated = self.datasource._propagate_trip_update_stop_events(
            stop_events,
            nominal_stop_times,
            treat_unexpected_stop_as_added_stop=False,
            treat_missing_stop_as_canceled_stop=False,
            is_complete_stop_sequence=True,
        )

        self.assertEqual([event["stop_sequence"] for event in propagated], ["10", "20"])
    def test_propagate_trip_update_stop_events_skips_propagation_without_nominal_stop_times(self):
        same_time = datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)
        stop_events = [
            {
                "stop_id": "s1",
                "stop_sequence": "10",
                "departure_time": same_time,
                "schedule_relationship": "SCHEDULED",
            }
        ]

        propagated = self.datasource._propagate_trip_update_stop_events(
            stop_events,
            [],
            treat_unexpected_stop_as_added_stop=True,
            treat_missing_stop_as_canceled_stop=True,
            is_complete_stop_sequence=True,
        )

        self.assertEqual(len(propagated), 1)
        self.assertEqual(propagated[0]["schedule_relationship"], "SCHEDULED")
    def test_propagate_trip_update_stop_events_orders_by_nominal_sequence(self):
        base_time = datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)
        stop_events = [
            {
                "stop_id": "s3",
                "departure_time": base_time.replace(minute=10),
                "schedule_relationship": "SCHEDULED",
            },
            {
                "stop_id": "s1",
                "departure_time": base_time.replace(minute=30),
                "schedule_relationship": "SCHEDULED",
            },
            {
                "stop_id": "s2",
                "departure_time": base_time.replace(minute=20),
                "schedule_relationship": "SKIPPED",
            },
        ]
        nominal_stop_times = [
            SimpleNamespace(stop_id="s1", stop_sequence=1, arrival_time=None, departure_time=base_time),
            SimpleNamespace(stop_id="s2", stop_sequence=2, arrival_time=None, departure_time=base_time),
            SimpleNamespace(stop_id="s3", stop_sequence=3, arrival_time=None, departure_time=base_time),
        ]

        propagated = self.datasource._propagate_trip_update_stop_events(
            stop_events,
            nominal_stop_times,
            treat_unexpected_stop_as_added_stop=False,
            treat_missing_stop_as_canceled_stop=False,
            is_complete_stop_sequence=True,
        )

        self.assertEqual([event["stop_id"] for event in propagated], ["s1", "s2", "s3"])
    def test_propagate_trip_update_stop_events_sorts_nominal_stop_times_by_sequence(self):
        base_time = datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)
        stop_events = [
            {
                "stop_id": "s1",
                "departure_time": base_time.replace(minute=30),
                "schedule_relationship": "SCHEDULED",
            },
            {
                "stop_id": "s3",
                "departure_time": base_time.replace(minute=10),
                "schedule_relationship": "SCHEDULED",
            },
            {
                "stop_id": "s2",
                "departure_time": base_time.replace(minute=20),
                "schedule_relationship": "SCHEDULED",
            },
        ]
        nominal_stop_times = [
            SimpleNamespace(stop_id="s3", stop_sequence=30, arrival_time=None, departure_time=base_time),
            SimpleNamespace(stop_id="s1", stop_sequence=10, arrival_time=None, departure_time=base_time),
            SimpleNamespace(stop_id="s2", stop_sequence=20, arrival_time=None, departure_time=base_time),
        ]

        propagated = self.datasource._propagate_trip_update_stop_events(
            stop_events,
            nominal_stop_times,
            treat_unexpected_stop_as_added_stop=False,
            treat_missing_stop_as_canceled_stop=False,
            is_complete_stop_sequence=True,
        )

        self.assertEqual([event["stop_id"] for event in propagated], ["s1", "s2", "s3"])
    def test_propagate_trip_update_stop_events_inserts_added_stops_by_departure_time(self):
        base_time = datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)
        stop_events = [
            {
                "stop_id": "s1",
                "departure_time": base_time,
                "schedule_relationship": "SCHEDULED",
            },
            {
                "stop_id": "s2",
                "departure_time": base_time.replace(minute=20),
                "schedule_relationship": "SCHEDULED",
            },
            {
                "stop_id": "sx",
                "departure_time": base_time.replace(minute=10),
                "schedule_relationship": "ADDED",
            },
        ]
        nominal_stop_times = [
            SimpleNamespace(stop_id="s1", stop_sequence=1, arrival_time=None, departure_time=base_time),
            SimpleNamespace(stop_id="s2", stop_sequence=2, arrival_time=None, departure_time=base_time),
        ]

        propagated = self.datasource._propagate_trip_update_stop_events(
            stop_events,
            nominal_stop_times,
            treat_unexpected_stop_as_added_stop=True,
            treat_missing_stop_as_canceled_stop=False,
            is_complete_stop_sequence=True,
        )

        self.assertEqual([event["stop_id"] for event in propagated], ["s1", "sx", "s2"])
    def test_propagate_trip_update_stop_events_orders_duplicate_stop_ids_by_time(self):
        base_time = datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)
        stop_events = [
            {
                "stop_id": "s1",
                "departure_time": base_time.replace(minute=40),
                "schedule_relationship": "SCHEDULED",
            },
            {
                "stop_id": "s1",
                "departure_time": base_time.replace(minute=5),
                "schedule_relationship": "SCHEDULED",
            },
        ]
        nominal_stop_times = [
            SimpleNamespace(stop_id="s1", stop_sequence=1, arrival_time=None, departure_time=base_time),
        ]

        propagated = self.datasource._propagate_trip_update_stop_events(
            stop_events,
            nominal_stop_times,
            treat_unexpected_stop_as_added_stop=False,
            treat_missing_stop_as_canceled_stop=False,
            is_complete_stop_sequence=True,
        )

        self.assertEqual(
            [event["departure_time"].minute for event in propagated],
            [5, 40],
        )
    def test_propagate_trip_update_stop_events_fixes_stop_id_on_stop_level_and_preserves_original(self):
        same_time = datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)
        stop_events = [
            {
                "stop_id": "de:1:2:3",
                "stop_sequence": "10",
                "departure_time": same_time,
                "schedule_relationship": "SCHEDULED",
                "is_valid": True,
            }
        ]
        nominal_stop_times = [
            SimpleNamespace(stop_id="de:1:2:4", stop_sequence=1, arrival_time=None, departure_time=same_time),
        ]

        propagated = self.datasource._propagate_trip_update_stop_events(
            stop_events,
            nominal_stop_times,
            treat_unexpected_stop_as_added_stop=False,
            treat_missing_stop_as_canceled_stop=False,
            is_complete_stop_sequence=True,
            incorrect_stop_id_handling=IncorrectStopIdHandling.FIX_TO_NOMINAL_STOP_ID,
        )

        self.assertEqual(len(propagated), 1)
        self.assertEqual(propagated[0]["stop_id"], "de:1:2:4")
        self.assertEqual(propagated[0]["original_stop_id"], "de:1:2:3")
    def test_propagate_trip_update_stop_events_does_not_fix_stop_id_when_handling_ignore(self):
        same_time = datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)
        stop_events = [
            {
                "stop_id": "de:1:2:3",
                "stop_sequence": "10",
                "departure_time": same_time,
                "schedule_relationship": "SCHEDULED",
                "is_valid": True,
            }
        ]
        nominal_stop_times = [
            SimpleNamespace(stop_id="de:1:2:4", stop_sequence=1, arrival_time=None, departure_time=same_time),
        ]

        propagated = self.datasource._propagate_trip_update_stop_events(
            stop_events,
            nominal_stop_times,
            treat_unexpected_stop_as_added_stop=False,
            treat_missing_stop_as_canceled_stop=False,
            is_complete_stop_sequence=True,
            incorrect_stop_id_handling=IncorrectStopIdHandling.IGNORE,
        )

        self.assertEqual(len(propagated), 1)
        self.assertEqual(propagated[0]["stop_id"], "de:1:2:3")
        self.assertNotIn("original_stop_id", propagated[0])

class TestMergeIncrementalStopEvents(unittest.TestCase):
    """Smoke tests for the incremental stop-event merge helper only."""

    def setUp(self):
        self.datasource = StopEventPropagationService()

    @staticmethod
    def _dt(minute, hour=8):
        return datetime(2026, 8, 1, hour, minute, tzinfo=timezone.utc)

    def _existing_events(self):
        return [
            {
                "stop_id": "s1",
                "stop_sequence": "1",
                "arrival_time": self._dt(0),
                "departure_time": self._dt(0),
                "scheduled_arrival_time": self._dt(0),
                "scheduled_departure_time": self._dt(0),
            },
            {
                "stop_id": "s2",
                "stop_sequence": "2",
                "arrival_time": self._dt(10),
                "departure_time": self._dt(11),
                "scheduled_arrival_time": self._dt(10),
                "scheduled_departure_time": self._dt(11),
            },
            {
                "stop_id": "s3",
                "stop_sequence": "3",
                "arrival_time": self._dt(20),
                "departure_time": self._dt(20),
                "scheduled_arrival_time": self._dt(20),
                "scheduled_departure_time": self._dt(20),
            },
        ]

    def test_returns_incoming_as_is_when_no_existing_baseline(self):
        incoming = [{"stop_id": "s1", "stop_sequence": "1"}]

        merged = self.datasource._merge_incremental_stop_events([], incoming)

        self.assertEqual(merged, incoming)
        self.assertIsNot(merged, incoming)

    def test_matches_primary_key_by_stop_id_and_stop_sequence(self):
        incoming = [
            {
                "stop_id": "s2",
                "stop_sequence": "2",
                "arrival_time": self._dt(15),
                "departure_time": self._dt(16),
                "scheduled_arrival_time": self._dt(10),
                "scheduled_departure_time": self._dt(11),
            }
        ]

        merged = self.datasource._merge_incremental_stop_events(self._existing_events(), incoming)

        self.assertEqual(merged[1]["arrival_time"], self._dt(15))
        self.assertEqual(merged[1]["departure_time"], self._dt(16))

    def test_falls_back_to_scheduled_time_when_stop_sequence_does_not_match(self):
        # incoming stop_sequence is "1" (positional in the batch), not "2" (its real position).
        incoming = [
            {
                "stop_id": "s2",
                "stop_sequence": "1",
                "arrival_time": self._dt(15),
                "departure_time": self._dt(16),
                "scheduled_arrival_time": self._dt(10),
                "scheduled_departure_time": self._dt(11),
            }
        ]

        merged = self.datasource._merge_incremental_stop_events(self._existing_events(), incoming)

        self.assertEqual(merged[1]["stop_id"], "s2")
        self.assertEqual(merged[1]["arrival_time"], self._dt(15))

    def test_unmatched_stop_id_is_appended_as_new(self):
        incoming = [{"stop_id": "unknown-stop", "stop_sequence": "99"}]

        merged = self.datasource._merge_incremental_stop_events(self._existing_events(), incoming)

        self.assertEqual(len(merged), 4)
        self.assertEqual(merged[-1]["stop_id"], "unknown-stop")

    def test_matched_stop_delay_propagates_to_later_stops(self):
        incoming = [
            {
                "stop_id": "s1",
                "stop_sequence": "1",
                "arrival_time": self._dt(0),
                "departure_time": self._dt(5),
                "scheduled_arrival_time": self._dt(0),
                "scheduled_departure_time": self._dt(0),
            }
        ]

        merged = self.datasource._merge_incremental_stop_events(self._existing_events(), incoming)

        self.assertEqual(merged[1]["arrival_time"], self._dt(15))
        self.assertEqual(merged[1]["departure_time"], self._dt(16))
        self.assertEqual(merged[2]["arrival_time"], self._dt(25))


class TestPropagateIncrementalDelay(unittest.TestCase):
    """Smoke tests for the pure per-stop delay propagation helper only."""

    def setUp(self):
        self.datasource = StopEventPropagationService()

    @staticmethod
    def _dt(minute, hour=8):
        return datetime(2026, 8, 1, hour, minute, tzinfo=timezone.utc)

    def test_propagates_delay_forward_through_arrival_and_departure(self):
        stop_events = [
            {
                "stop_id": "s1",
                "arrival_time": self._dt(8),
                "departure_time": self._dt(8),
                "scheduled_arrival_time": self._dt(0),
                "scheduled_departure_time": self._dt(0),
            },
            {
                "stop_id": "s2",
                "scheduled_arrival_time": self._dt(10),
                "scheduled_departure_time": self._dt(11),
            },
            {
                "stop_id": "s3",
                "scheduled_arrival_time": self._dt(20),
                "scheduled_departure_time": self._dt(20),
            },
        ]

        self.datasource._propagate_incremental_delay(stop_events, {0})

        self.assertEqual(stop_events[1]["arrival_time"], self._dt(18))
        self.assertEqual(stop_events[1]["departure_time"], self._dt(19))
        self.assertEqual(stop_events[2]["arrival_time"], self._dt(28))
        self.assertEqual(stop_events[2]["departure_time"], self._dt(28))

    def test_does_not_touch_stops_without_any_scheduled_time(self):
        stop_events = [
            {
                "stop_id": "s1",
                "arrival_time": self._dt(8),
                "departure_time": self._dt(8),
                "scheduled_arrival_time": self._dt(0),
                "scheduled_departure_time": self._dt(0),
            },
            {"stop_id": "s2"},
        ]

        self.datasource._propagate_incremental_delay(stop_events, {0})

        self.assertNotIn("arrival_time", stop_events[1])
        self.assertNotIn("departure_time", stop_events[1])

    def test_running_early_is_floored_to_scheduled_departure_at_timepoint(self):
        stop_events = [
            {
                "stop_id": "s1",
                "arrival_time": self._dt(7),
                "departure_time": self._dt(7),
                "scheduled_arrival_time": self._dt(10),
                "scheduled_departure_time": self._dt(10),
            },
            {
                "stop_id": "s2",
                # timepoint dwell: scheduled departure is later than scheduled arrival
                "scheduled_arrival_time": self._dt(30),
                "scheduled_departure_time": self._dt(32),
            },
        ]

        self.datasource._propagate_incremental_delay(stop_events, {0})

        self.assertEqual(stop_events[1]["arrival_time"], self._dt(27))
        self.assertEqual(stop_events[1]["departure_time"], self._dt(32))

    def test_running_late_is_never_clamped_at_timepoint(self):
        stop_events = [
            {
                "stop_id": "s1",
                "arrival_time": self._dt(13),
                "departure_time": self._dt(13),
                "scheduled_arrival_time": self._dt(10),
                "scheduled_departure_time": self._dt(10),
            },
            {
                "stop_id": "s2",
                "scheduled_arrival_time": self._dt(30),
                "scheduled_departure_time": self._dt(32),
            },
        ]

        self.datasource._propagate_incremental_delay(stop_events, {0})

        self.assertEqual(stop_events[1]["arrival_time"], self._dt(33))
        self.assertEqual(stop_events[1]["departure_time"], self._dt(35))

    def test_terminus_without_scheduled_departure_mirrors_propagated_arrival(self):
        stop_events = [
            {
                "stop_id": "s1",
                "arrival_time": self._dt(8),
                "departure_time": self._dt(8),
                "scheduled_arrival_time": self._dt(0),
                "scheduled_departure_time": self._dt(0),
            },
            {
                "stop_id": "terminus",
                "scheduled_arrival_time": self._dt(20),
                "scheduled_departure_time": None,
            },
        ]

        self.datasource._propagate_incremental_delay(stop_events, {0})

        self.assertEqual(stop_events[1]["arrival_time"], self._dt(28))
        self.assertEqual(stop_events[1]["departure_time"], self._dt(28))

    def test_origin_without_scheduled_arrival_mirrors_propagated_departure(self):
        stop_events = [
            {
                "stop_id": "s1",
                "arrival_time": self._dt(8),
                "departure_time": self._dt(8),
                "scheduled_arrival_time": self._dt(0),
                "scheduled_departure_time": self._dt(0),
            },
            {
                "stop_id": "origin-like",
                "scheduled_arrival_time": None,
                "scheduled_departure_time": self._dt(20),
            },
        ]

        self.datasource._propagate_incremental_delay(stop_events, {0})

        self.assertEqual(stop_events[1]["arrival_time"], self._dt(28))
        self.assertEqual(stop_events[1]["departure_time"], self._dt(28))

    def test_segment_resets_at_each_matched_stop(self):
        stop_events = [
            {
                "stop_id": "s1",
                "arrival_time": self._dt(8),
                "departure_time": self._dt(8),
                "scheduled_arrival_time": self._dt(0),
                "scheduled_departure_time": self._dt(0),
            },
            {
                "stop_id": "s2",
                "scheduled_arrival_time": self._dt(10),
                "scheduled_departure_time": self._dt(10),
            },
            {
                "stop_id": "s3",
                "arrival_time": self._dt(21),
                "departure_time": self._dt(21),
                "scheduled_arrival_time": self._dt(20),
                "scheduled_departure_time": self._dt(20),
            },
            {
                "stop_id": "s4",
                "scheduled_arrival_time": self._dt(30),
                "scheduled_departure_time": self._dt(30),
            },
        ]

        self.datasource._propagate_incremental_delay(stop_events, {0, 2})

        self.assertEqual(stop_events[1]["arrival_time"], self._dt(18))
        self.assertEqual(stop_events[3]["arrival_time"], self._dt(31))

    def test_inconsistent_departure_before_arrival_falls_back_to_arrival_reference(self):
        stop_events = [
            {
                "stop_id": "s1",
                # invalid/reversed: departure earlier than arrival at the same stop
                "arrival_time": self._dt(10),
                "departure_time": self._dt(2),
                "scheduled_arrival_time": self._dt(5),
                "scheduled_departure_time": self._dt(0),
            },
            {
                "stop_id": "s2",
                "scheduled_arrival_time": self._dt(20),
                "scheduled_departure_time": self._dt(20),
            },
        ]

        self.datasource._propagate_incremental_delay(stop_events, {0})

        # delay is derived from arrival (10 - 5 = +5 min), not the inconsistent departure.
        self.assertEqual(stop_events[1]["arrival_time"], self._dt(25))

    def test_no_matched_indexes_does_nothing(self):
        stop_events = [{"stop_id": "s1", "scheduled_arrival_time": self._dt(0)}]

        self.datasource._propagate_incremental_delay(stop_events, set())

        self.assertNotIn("arrival_time", stop_events[0])

