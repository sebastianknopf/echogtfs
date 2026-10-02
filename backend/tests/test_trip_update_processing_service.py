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
from echogtfs.services.realtimeprocessing.trip_update_processing_service import TripUpdateProcessingService

class TestTripUpdateProcessingService(unittest.IsolatedAsyncioTestCase):
    async def test_sync_trip_update_records_upserts_trip_updates(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={
                "agency": {"a1"},
                "route": {"r1", "mapped-route"},
                "stop": {"s1", "mapped-stop"},
                "trip": {"trip-1"},
            }
        )
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 2,
            apply_mapping=lambda entity: {
                **entity,
                "route_id": "mapped-route" if entity.get("route_id") == "r1" else entity.get("route_id"),
                "stop_id": "mapped-stop" if entity.get("stop_id") == "stop-1" else entity.get("stop_id"),
            },
        )

        records = [
            {
                "id": "trip-upd-1",
                "trip_id": "trip-1",
                "scheduled_start_stop_id": "stop-1",
                "scheduled_end_stop_id": "stop-2",
                "scheduled_start_time": datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc),
                "scheduled_end_time": datetime(2026, 8, 1, 9, 0, 0, tzinfo=timezone.utc),
                "start_time": "08:00:00",
                "start_date": "20260801",
                "route_id": "r1",
                "schedule_relationship": "SCHEDULED",
                "assignment_type": "ASSIGNED",
                "is_active": True,
                "is_valid": True,
                "stop_events": [
                    {
                        "stop_id": "stop-1",
                        "stop_sequence": "1",
                        "arrival_time": "2026-08-01T08:00:00Z",
                        "departure_time": "2026-08-01T08:01:00Z",
                        "schedule_relationship": "SCHEDULED",
                        "is_valid": True,
                    }
                ],
            }
        ]

        result = await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        self.assertEqual(result, {"added": 1, "updated": 0, "deleted": 0})
        realtime_repository.update_trip_update_from_sync.assert_awaited_once()
        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertEqual(kwargs["trip_id"], "trip-1")
        self.assertEqual(kwargs["original_trip_id"], "trip-1")
        self.assertEqual(kwargs["scheduled_start_stop_id"], "mapped-stop")
        self.assertEqual(kwargs["scheduled_end_stop_id"], "stop-2")
        self.assertEqual(kwargs["scheduled_start_time"], datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(kwargs["scheduled_end_time"], datetime(2026, 8, 1, 9, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(kwargs["route_id"], "mapped-route")
        self.assertEqual(kwargs["stop_events"][0]["stop_id"], "mapped-stop")
        self.assertEqual(kwargs["assignment_type"], "DIRECT_BY_ID")
        self.assertTrue(kwargs["is_active_on_create"])
        datasource._matching_service.match.assert_not_awaited()
    async def test_sync_trip_update_records_calls_matching_for_non_nominal_trip(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"nominal-trip"}}
        )
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._caching_service = SimpleNamespace(
            put_trip_id=AsyncMock(),
            pop_trip_id=AsyncMock(),
        )
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=("matched-trip-1", AssignmentType.MATCHED_BY_START_STOP))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        records = [
            {
                "id": "trip-upd-1",
                "trip_id": "external-trip-1",
                "start_time": "08:00:00",
                "start_date": "20260801",
                "route_id": "r1",
                "stop_events": [],
            }
        ]

        result = await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        self.assertEqual(result, {"added": 1, "updated": 0, "deleted": 0})
        datasource._matching_service.match.assert_awaited_once()
        realtime_repository.delete_trips_by_trip_ids.assert_awaited_once_with(["external-trip-1"])
        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertEqual(kwargs["trip_id"], "matched-trip-1")
        self.assertEqual(kwargs["assignment_type"], "MATCHED_BY_START_STOP")
        datasource._caching_service.put_trip_id.assert_awaited_once_with(
            "external-trip-1",
            "matched-trip-1",
        )
    async def test_sync_trip_update_records_sets_invalid_and_deactivates_when_trip_unmatched(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={
                "agency": {"a1"},
                "route": {"r1"},
                "stop": {"s1"},
                "trip": {"nominal-trip"},
            }
        )
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        records = [
            {
                "id": "trip-upd-1",
                "trip_id": "external-trip-1",
                "start_time": "08:00:00",
                "start_date": "20260801",
                "route_id": "r1",
                "is_active": True,
                "is_valid": True,
                "stop_events": [],
            }
        ]

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertFalse(kwargs["is_trip_valid"])
        self.assertTrue(kwargs["is_route_valid"])
        self.assertFalse(kwargs["is_active_on_create"])
        self.assertEqual(kwargs["assignment_type"], "NO_MATCH_GENERAL")
    async def test_sync_trip_update_records_discards_entire_object_and_deletes_existing_when_policy_requires(self):
        repository = _SystemRepositoryStub()
        repository.get_data_source_invalid_reference_policy = AsyncMock(
            return_value=InvalidReferencePolicy.DISCARD_ENTIRE_OBJECT
        )
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        trip_uuid = datasource._make_unique_id("trip-1", "Demo")
        realtime_repository.list_trips_for_data_source = AsyncMock(
            return_value=[SimpleNamespace(id=trip_uuid, data_source_id=2)]
        )

        records = [
            {
                "id": "trip-upd-1",
                "trip_id": "trip-1",
                "start_time": "08:00:00",
                "start_date": "20260801",
                "route_id": "invalid-route",
                "stop_events": [],
            }
        ]

        result = await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        self.assertEqual(result, {"added": 0, "updated": 0, "deleted": 1})
        realtime_repository.update_trip_update_from_sync.assert_not_awaited()
        realtime_repository.delete_trips_for_data_source_by_ids.assert_awaited()
    async def test_sync_trip_update_records_keeps_matched_trip_from_previous_run(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._caching_service = SimpleNamespace(
            put_trip_id=AsyncMock(),
            pop_trip_id=AsyncMock(),
        )
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=("trip-1", AssignmentType.MATCHED_BY_START_STOP))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        matched_trip_uuid = datasource._make_unique_id("trip-1", "Demo")
        realtime_repository.list_trips_for_data_source = AsyncMock(
            return_value=[
                SimpleNamespace(id=matched_trip_uuid, data_source_id=2, is_active=True)
            ]
        )

        records = [
            {
                "id": "external-trip-1",
                "trip_id": "external-trip-1",
                "start_time": "08:00:00",
                "start_date": "20260801",
                "route_id": "r1",
                "stop_events": [],
            }
        ]

        result = await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        self.assertEqual(result["deleted"], 0)
        realtime_repository.delete_trips_for_data_source_by_ids.assert_not_awaited()

        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertEqual(kwargs["trip_uuid"], matched_trip_uuid)
        self.assertEqual(kwargs["trip_id"], "trip-1")
        self.assertEqual(kwargs["assignment_type"], AssignmentType.MATCHED_BY_START_STOP.value)
        datasource._caching_service.put_trip_id.assert_awaited_once_with(
            "external-trip-1",
            "trip-1",
        )
    async def test_sync_trip_update_records_preserves_existing_trip_activation_for_invalid_stop(self):
        repository = _SystemRepositoryStub()
        repository.get_data_source_invalid_reference_policy = AsyncMock(
            return_value=InvalidReferencePolicy.KEEP_OBJECT_DISABLED
        )
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        trip_uuid = datasource._make_unique_id("trip-1", "Demo")
        existing_trip = SimpleNamespace(
            id=trip_uuid,
            trip_id="trip-1",
            data_source_id=2,
            is_active=True,
        )
        realtime_repository.list_trips_for_data_source = AsyncMock(return_value=[existing_trip])
        realtime_repository.list_trips_by_trip_ids = AsyncMock(return_value=[existing_trip])

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=[
                {
                    "id": "trip-upd-1",
                    "trip_id": "trip-1",
                    "start_time": "08:00:00",
                    "start_date": "20260801",
                    "route_id": "r1",
                    "stop_events": [
                        {
                            "stop_id": "invalid-stop",
                            "stop_sequence": "1",
                            "arrival_time": None,
                            "departure_time": None,
                            "schedule_relationship": "SCHEDULED",
                        }
                    ],
                }
            ],
        )

        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertTrue(existing_trip.is_active)
        self.assertTrue(kwargs["is_active_on_create"])
    async def test_sync_trip_update_records_preserves_existing_inactive_trip_for_invalid_stop(self):
        repository = _SystemRepositoryStub()
        repository.get_data_source_invalid_reference_policy = AsyncMock(
            return_value=InvalidReferencePolicy.KEEP_OBJECT_DISABLED
        )
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        trip_uuid = datasource._make_unique_id("trip-1", "Demo")
        existing_trip = SimpleNamespace(
            id=trip_uuid,
            trip_id="trip-1",
            data_source_id=2,
            is_active=False,
        )
        realtime_repository.list_trips_for_data_source = AsyncMock(return_value=[existing_trip])
        realtime_repository.list_trips_by_trip_ids = AsyncMock(return_value=[existing_trip])

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=[
                {
                    "id": "trip-upd-1",
                    "trip_id": "trip-1",
                    "start_time": "08:00:00",
                    "start_date": "20260801",
                    "route_id": "r1",
                    "stop_events": [
                        {
                            "stop_id": "invalid-stop",
                            "stop_sequence": "1",
                            "arrival_time": None,
                            "departure_time": None,
                            "schedule_relationship": "SCHEDULED",
                        }
                    ],
                }
            ],
        )

        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertFalse(existing_trip.is_active)
        self.assertFalse(kwargs["is_active_on_create"])
    async def test_sync_trip_update_records_marks_unexpected_as_added_when_enabled(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={
                "agency": {"a1"},
                "route": {"r1"},
                "stop": {"s1", "s-extra"},
                "trip": {"trip-1"},
            }
        )
        datasource = make_processor(TripUpdateProcessingService, {"treat_unexpected_stop_as_added_stop": True})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        gtfs_repository.get_gtfs_trip_with_stop_times = AsyncMock(
            return_value=SimpleNamespace(
                gtfs_id="trip-1",
                stop_times=[SimpleNamespace(stop_id="s1", stop_sequence=1, arrival_time=None, departure_time=None)],
            )
        )

        records = [
            {
                "id": "trip-upd-1",
                "trip_id": "trip-1",
                "start_time": "08:00:00",
                "start_date": "20260801",
                "route_id": "r1",
                "stop_events": [
                    {
                        "stop_id": "s-extra",
                        "stop_sequence": "1",
                        "arrival_time": "2026-08-01T08:00:00Z",
                        "departure_time": "2026-08-01T08:01:00Z",
                        "is_valid": True,
                    }
                ],
            }
        ]

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        added_events = [
            event for event in kwargs["stop_events"]
            if event.get("schedule_relationship") == "ADDED"
        ]
        self.assertEqual(len(added_events), 1)
        self.assertEqual(added_events[0]["stop_id"], "s-extra")
    async def test_sync_trip_update_records_adds_missing_as_skipped_when_enabled(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {"treat_missing_stop_as_canceled_stop": True})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        nominal_stop_1 = SimpleNamespace(
            stop_id="s1",
            stop_sequence=1,
            arrival_time=datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc),
            departure_time=datetime(2026, 8, 1, 8, 1, tzinfo=timezone.utc),
        )
        nominal_stop_2 = SimpleNamespace(
            stop_id="s2",
            stop_sequence=2,
            arrival_time=datetime(2026, 8, 1, 8, 10, tzinfo=timezone.utc),
            departure_time=datetime(2026, 8, 1, 8, 11, tzinfo=timezone.utc),
        )
        gtfs_repository.get_gtfs_trip_with_stop_times = AsyncMock(
            return_value=SimpleNamespace(gtfs_id="trip-1", stop_times=[nominal_stop_1, nominal_stop_2])
        )

        records = [
            {
                "id": "trip-upd-1",
                "trip_id": "trip-1",
                "start_time": "08:00:00",
                "start_date": "20260801",
                "route_id": "r1",
                "stop_events": [
                    {
                        "stop_id": "s1",
                        "stop_sequence": "1",
                        "arrival_time": "2026-08-01T08:00:00Z",
                        "departure_time": "2026-08-01T08:01:00Z",
                        "is_valid": True,
                    }
                ],
            }
        ]

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        skipped_events = [e for e in kwargs["stop_events"] if e.get("schedule_relationship") == "SKIPPED"]
        self.assertEqual(len(skipped_events), 1)
        self.assertEqual(skipped_events[0]["stop_id"], "s2")
    async def test_sync_trip_update_records_discards_unexpected_stops_when_flag_disabled(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        nominal_stop_1 = SimpleNamespace(
            stop_id="s1",
            stop_sequence=1,
            arrival_time=datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc),
            departure_time=datetime(2026, 8, 1, 8, 1, tzinfo=timezone.utc),
        )
        gtfs_repository.get_gtfs_trip_with_stop_times = AsyncMock(
            return_value=SimpleNamespace(gtfs_id="trip-1", stop_times=[nominal_stop_1])
        )

        records = [
            {
                "id": "trip-upd-1",
                "trip_id": "trip-1",
                "start_time": "08:00:00",
                "start_date": "20260801",
                "route_id": "r1",
                "is_complete_stop_sequence": True,
                "stop_events": [
                    {
                        "stop_id": "s-extra",
                        "stop_sequence": "99",
                        "arrival_time": "2026-08-01T08:00:00Z",
                        "departure_time": "2026-08-01T08:01:00Z",
                        "is_valid": True,
                    }
                ],
            }
        ]

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertEqual(len(kwargs["stop_events"]), 1)
        self.assertEqual(kwargs["stop_events"][0]["stop_id"], "s1")
        self.assertEqual(kwargs["stop_events"][0]["schedule_relationship"], "NO_DATA")
    async def test_sync_trip_update_records_merges_complete_sequence_order(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {"treat_missing_stop_as_canceled_stop": True})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        nominal_stop_1 = SimpleNamespace(
            stop_id="s1",
            stop_sequence=1,
            arrival_time=datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc),
            departure_time=datetime(2026, 8, 1, 8, 1, tzinfo=timezone.utc),
        )
        nominal_stop_2 = SimpleNamespace(
            stop_id="s2",
            stop_sequence=2,
            arrival_time=datetime(2026, 8, 1, 8, 10, tzinfo=timezone.utc),
            departure_time=datetime(2026, 8, 1, 8, 11, tzinfo=timezone.utc),
        )
        gtfs_repository.get_gtfs_trip_with_stop_times = AsyncMock(
            return_value=SimpleNamespace(gtfs_id="trip-1", stop_times=[nominal_stop_1, nominal_stop_2])
        )

        records = [
            {
                "id": "trip-upd-1",
                "trip_id": "trip-1",
                "start_time": "08:00:00",
                "start_date": "20260801",
                "route_id": "r1",
                "is_complete_stop_sequence": True,
                "stop_events": [
                    {
                        "stop_id": "s1",
                        "stop_sequence": "8",
                        "arrival_time": "2026-08-01T08:00:00Z",
                        "departure_time": "2026-08-01T08:01:00Z",
                        "is_valid": True,
                    }
                ],
            }
        ]

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertEqual([e["stop_id"] for e in kwargs["stop_events"]], ["s1", "s2"])
        self.assertEqual([e["stop_sequence"] for e in kwargs["stop_events"]], ["1", "2"])
    async def test_sync_trip_update_records_merges_incremental_into_existing_complete_trip(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1", "s2", "s3"}, "trip": {"trip-1"}}
        )

        trip_uuid = datasource._make_unique_id("trip-1", "Demo")
        scheduled_start = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
        scheduled_end = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
        existing_trip = SimpleNamespace(
            id=trip_uuid,
            trip_id="trip-1",
            data_source_id=2,
            is_active=True,
            is_complete_stop_sequence=True,
            scheduled_start_time=scheduled_start,
            scheduled_end_time=scheduled_end,
            scheduled_start_stop_id="s1",
            scheduled_end_stop_id="s3",
            start_time="08:00:00",
        )
        realtime_repository.list_trips_for_data_source = AsyncMock(return_value=[existing_trip])
        realtime_repository.list_trips_by_trip_ids = AsyncMock(return_value=[existing_trip])

        existing_stop_event = SimpleNamespace(
            stop_id="s2",
            original_stop_id="s2",
            stop_sequence="2",
            arrival_time=datetime(2026, 8, 1, 8, 10, tzinfo=timezone.utc),
            departure_time=datetime(2026, 8, 1, 8, 11, tzinfo=timezone.utc),
            scheduled_arrival_time=datetime(2026, 8, 1, 8, 10, tzinfo=timezone.utc),
            scheduled_departure_time=datetime(2026, 8, 1, 8, 11, tzinfo=timezone.utc),
            schedule_relationship="SCHEDULED",
            is_implied_schedule_relationship=False,
            is_valid=True,
        )
        realtime_repository.list_stop_events_for_trip = AsyncMock(return_value=[existing_stop_event])

        records = [
            {
                "id": "trip-upd-1",
                "trip_id": "trip-1",
                "start_time": None,
                "start_date": "20260801",
                "route_id": "r1",
                "is_complete_stop_sequence": False,
                "stop_events": [
                    {
                        "stop_id": "s2",
                        "stop_sequence": "2",
                        "arrival_time": datetime(2026, 8, 1, 8, 15, tzinfo=timezone.utc),
                        "departure_time": datetime(2026, 8, 1, 8, 16, tzinfo=timezone.utc),
                        "scheduled_arrival_time": datetime(2026, 8, 1, 8, 10, tzinfo=timezone.utc),
                        "scheduled_departure_time": datetime(2026, 8, 1, 8, 11, tzinfo=timezone.utc),
                        "is_valid": True,
                    }
                ],
            }
        ]

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        realtime_repository.list_stop_events_for_trip.assert_awaited_once()
        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertTrue(kwargs["is_complete_stop_sequence"])
        self.assertEqual(kwargs["scheduled_start_time"], scheduled_start)
        self.assertEqual(kwargs["scheduled_end_time"], scheduled_end)
        self.assertEqual(kwargs["scheduled_start_stop_id"], "s1")
        self.assertEqual(kwargs["scheduled_end_stop_id"], "s3")
        self.assertEqual(kwargs["start_time"], "08:00:00")
        self.assertEqual(len(kwargs["stop_events"]), 1)
        self.assertEqual(
            kwargs["stop_events"][0]["arrival_time"],
            datetime(2026, 8, 1, 8, 15, tzinfo=timezone.utc),
        )
    async def test_sync_trip_update_records_incomplete_without_existing_baseline_stores_as_is(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        records = [
            {
                "id": "trip-upd-1",
                "trip_id": "trip-1",
                "start_time": None,
                "start_date": "20260801",
                "route_id": "r1",
                "is_complete_stop_sequence": False,
                "stop_events": [
                    {
                        "stop_id": "s1",
                        "stop_sequence": "5",
                        "arrival_time": datetime(2026, 8, 1, 8, 15, tzinfo=timezone.utc),
                        "departure_time": datetime(2026, 8, 1, 8, 16, tzinfo=timezone.utc),
                        "is_valid": True,
                    }
                ],
            }
        ]

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        realtime_repository.list_stop_events_for_trip.assert_not_awaited()
        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertFalse(kwargs["is_complete_stop_sequence"])
        self.assertIsNone(kwargs["scheduled_start_time"])
        self.assertIsNone(kwargs["scheduled_end_time"])
        self.assertIsNone(kwargs["scheduled_start_stop_id"])
        self.assertIsNone(kwargs["scheduled_end_stop_id"])
        self.assertIsNone(kwargs["start_time"])
        self.assertEqual(kwargs["stop_events"][0]["stop_sequence"], "")
    async def test_sync_trip_update_records_incomplete_with_existing_incomplete_trip_does_not_merge(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        trip_uuid = datasource._make_unique_id("trip-1", "Demo")
        existing_trip = SimpleNamespace(
            id=trip_uuid,
            trip_id="trip-1",
            data_source_id=2,
            is_active=True,
            is_complete_stop_sequence=False,
            scheduled_start_time=None,
            scheduled_end_time=None,
            scheduled_start_stop_id=None,
            scheduled_end_stop_id=None,
            start_time=None,
        )
        realtime_repository.list_trips_for_data_source = AsyncMock(return_value=[existing_trip])
        realtime_repository.list_trips_by_trip_ids = AsyncMock(return_value=[existing_trip])

        records = [
            {
                "id": "trip-upd-1",
                "trip_id": "trip-1",
                "start_time": None,
                "start_date": "20260801",
                "route_id": "r1",
                "is_complete_stop_sequence": False,
                "stop_events": [
                    {
                        "stop_id": "s1",
                        "stop_sequence": "5",
                        "arrival_time": datetime(2026, 8, 1, 8, 15, tzinfo=timezone.utc),
                        "departure_time": datetime(2026, 8, 1, 8, 16, tzinfo=timezone.utc),
                        "is_valid": True,
                    }
                ],
            }
        ]

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        realtime_repository.list_stop_events_for_trip.assert_not_awaited()
        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertFalse(kwargs["is_complete_stop_sequence"])
        self.assertEqual(kwargs["stop_events"][0]["stop_sequence"], "")
    async def test_sync_trip_update_records_is_differential_updates_keeps_untouched_trips(self):
        repository = _SystemRepositoryStub()
        repository.get_data_source_is_differential_updates = AsyncMock(return_value=True)
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        untouched_trip_uuid = datasource._make_unique_id("trip-old", "Demo")
        untouched_trip = SimpleNamespace(
            id=untouched_trip_uuid,
            trip_id="trip-old",
            data_source_id=2,
            is_active=True,
            is_complete_stop_sequence=True,
            original_trip_id="trip-old",
        )
        realtime_repository.list_trips_for_data_source = AsyncMock(return_value=[untouched_trip])
        realtime_repository.list_trips_by_trip_ids = AsyncMock(return_value=[])

        records: list[dict] = []

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        realtime_repository.delete_trips_for_data_source_by_ids.assert_not_awaited()
    async def test_sync_trip_update_records_deletes_untouched_trips_when_not_differential(self):
        repository = _SystemRepositoryStub()
        repository.get_data_source_is_differential_updates = AsyncMock(return_value=False)
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(TripUpdateProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        untouched_trip_uuid = datasource._make_unique_id("trip-old", "Demo")
        untouched_trip = SimpleNamespace(
            id=untouched_trip_uuid,
            trip_id="trip-old",
            data_source_id=2,
            is_active=True,
            is_complete_stop_sequence=True,
            original_trip_id="trip-old",
        )
        realtime_repository.list_trips_for_data_source = AsyncMock(return_value=[untouched_trip])
        realtime_repository.list_trips_by_trip_ids = AsyncMock(return_value=[])

        records: list[dict] = []

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        realtime_repository.delete_trips_for_data_source_by_ids.assert_awaited_once_with(
            2, [untouched_trip_uuid]
        )