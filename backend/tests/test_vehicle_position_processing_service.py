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
from echogtfs.services.realtimeprocessing.vehicle_position_processing_service import VehiclePositionProcessingService

class TestVehiclePositionProcessingService(unittest.IsolatedAsyncioTestCase):
    async def test_sync_vehicle_position_records_upserts_vehicle_positions(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={
                "agency": {"a1"},
                "route": {"r1", "mapped-route"},
                "stop": {"s1"},
                "trip": {"trip-1"},
            }
        )
        datasource = make_processor(VehiclePositionProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 1,
            apply_mapping=lambda entity: {
                **entity,
                "route_id": "mapped-route" if entity.get("route_id") == "r1" else entity.get("route_id"),
            },
        )

        records = [
            {
                "id": "veh-upd-1",
                "trip": {
                    "trip_id": "trip-1",
                    "start_time": "08:00:00",
                    "start_date": "20260801",
                    "route_id": "r1",
                    "schedule_relationship": "SCHEDULED",
                    "assignment_type": "ASSIGNED",
                },
                "vehicle_id": "vehicle-1",
                "vehicle_label": "bus-1",
                "vehicle_license_plate": None,
                "vehicle_wheelchair_accessible": "NO_VALUE",
                "timestamp": "2026-08-01T08:05:00Z",
                "latitude": 47.1,
                "longitude": 8.5,
                "current_stop_sequence": 4,
                "current_status": "IN_TRANSIT_TO",
                "assignment_type": "ASSIGNED",
                "congestion_level": "UNKNOWN_CONGESTION_LEVEL",
                "is_active": True,
                "is_valid": True,
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
        realtime_repository.update_vehicle_position_from_sync.assert_awaited_once()
        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertEqual(kwargs["trip_id"], "trip-1")
        self.assertEqual(kwargs["trip_route_id"], "mapped-route")
        self.assertEqual(kwargs["vehicle_id"], "vehicle-1")
        self.assertEqual(kwargs["trip_assignment_type"], "DIRECT_BY_ID")
        self.assertIn("trip_scheduled_start_stop_id", kwargs)
        self.assertNotIn("assignment_type", kwargs)
        datasource._matching_service.match.assert_not_awaited()
    async def test_sync_vehicle_position_records_sets_no_match_assignment_when_matching_fails(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"nominal-trip"}}
        )
        datasource = make_processor(VehiclePositionProcessingService, {})
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
                "id": "veh-upd-1",
                "trip": {
                    "trip_id": "external-trip-1",
                    "start_time": "08:00:00",
                    "start_date": "20260801",
                    "route_id": "r1",
                },
                "vehicle_id": "vehicle-1",
                "timestamp": "2026-08-01T08:05:00Z",
                "latitude": 47.1,
                "longitude": 8.5,
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
        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertEqual(kwargs["trip_assignment_type"], "NO_MATCH_GENERAL")
    async def test_sync_vehicle_position_records_discards_record_without_trip_object(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(VehiclePositionProcessingService, {})
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
                "id": "veh-upd-1",
                "vehicle_id": "vehicle-1",
                "timestamp": "2026-08-01T08:05:00Z",
                "latitude": 47.1,
                "longitude": 8.5,
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

        self.assertEqual(result, {"added": 0, "updated": 0, "deleted": 0})
        realtime_repository.update_vehicle_position_from_sync.assert_not_awaited()
    async def test_sync_vehicle_position_records_uses_trip_scheduled_fields_for_matching(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"nominal-trip"}}
        )
        datasource = make_processor(VehiclePositionProcessingService, {})
        datasource._caching_service = SimpleNamespace(
            put_trip_id=AsyncMock(),
            pop_trip_id=AsyncMock(),
        )
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=("matched-trip-1", AssignmentType.MATCHED_BY_INTERMEDIATE_STOPS))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: {**entity, "stop_id": "s1" if entity.get("stop_id") else entity.get("stop_id")},
        )

        records = [
            {
                "id": "veh-upd-1",
                "scheduled_start_time": datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc),
                "scheduled_end_time": datetime(2026, 8, 1, 8, 5, tzinfo=timezone.utc),
                "scheduled_start_stop_id": "s1",
                "scheduled_end_stop_id": "s1",
                "trip": {
                    "trip_id": "external-trip-1",
                    "start_time": "08:00:00",
                    "start_date": "20260801",
                    "route_id": "r1",
                },
                "vehicle_id": "vehicle-1",
                "timestamp": "2026-08-01T08:05:00Z",
                "latitude": 47.1,
                "longitude": 8.5,
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

        datasource._matching_service.match.assert_awaited_once()
        realtime_repository.delete_trips_by_trip_ids.assert_not_awaited()
        match_kwargs = datasource._matching_service.match.await_args.kwargs
        self.assertIsNotNone(match_kwargs["scheduled_start_time"])
        self.assertIsNotNone(match_kwargs["scheduled_end_time"])
        self.assertEqual(match_kwargs["scheduled_start_stop_id"], "s1")
        self.assertEqual(match_kwargs["scheduled_end_stop_id"], "s1")
        self.assertTrue(match_kwargs["is_complete_stop_sequence"])
        self.assertEqual(
            match_kwargs["intermediate_stop_sample_size"],
            VehiclePositionProcessingService.MAX_INTERMEDIATE_STOP_SAMPLE_SIZE,
        )
        self.assertEqual(VehiclePositionProcessingService.MAX_INTERMEDIATE_STOP_SAMPLE_SIZE, 3)
        datasource._caching_service.put_trip_id.assert_awaited_once_with(
            "external-trip-1",
            "matched-trip-1",
        )

    async def test_sync_vehicle_position_records_keeps_matched_vehicle_from_previous_run(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"nominal-trip"}}
        )
        datasource = make_processor(VehiclePositionProcessingService, {})
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

        existing_vehicle_uuid = datasource._make_unique_id("persisted-vehicle", "Demo")
        realtime_repository.list_vehicles_for_data_source = AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=existing_vehicle_uuid,
                    data_source_id=2,
                    trip_id="matched-trip-1",
                )
            ]
        )

        records = [
            {
                "id": "veh-upd-1",
                "trip": {
                    "trip_id": "external-trip-1",
                    "start_time": "08:00:00",
                    "start_date": "20260801",
                    "route_id": "r1",
                },
                "vehicle_id": "vehicle-1",
                "timestamp": "2026-08-01T08:05:00Z",
                "latitude": 47.1,
                "longitude": 8.5,
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
        realtime_repository.delete_vehicles_for_data_source_by_ids.assert_not_awaited()

        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertEqual(kwargs["vehicle_uuid"], existing_vehicle_uuid)
        self.assertEqual(kwargs["trip_id"], "matched-trip-1")
        datasource._caching_service.put_trip_id.assert_awaited_once_with(
            "external-trip-1",
            "matched-trip-1",
        )
    async def test_sync_vehicle_position_records_sets_invalid_when_route_reference_invalid(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={
                "agency": {"a1"},
                "route": {"r1"},
                "stop": {"s1"},
                "trip": {"trip-1"},
            }
        )
        datasource = make_processor(VehiclePositionProcessingService, {})
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
                "id": "veh-upd-1",
                "trip": {
                    "trip_id": "trip-1",
                    "start_time": "08:00:00",
                    "start_date": "20260801",
                    "route_id": "invalid-route",
                },
                "vehicle_id": "vehicle-1",
                "timestamp": "2026-08-01T08:05:00Z",
                "latitude": 47.1,
                "longitude": 8.5,
                "is_valid": True,
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

        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertNotIn("is_valid", kwargs)
        self.assertTrue(kwargs["trip_is_trip_valid"])
        self.assertFalse(kwargs["trip_is_route_valid"])
        self.assertEqual(kwargs["trip_route_id"], "")
    async def test_sync_vehicle_position_records_discards_entire_object_and_deletes_existing_when_policy_requires(self):
        repository = _SystemRepositoryStub()
        repository.get_data_source_invalid_reference_policy = AsyncMock(
            return_value=InvalidReferencePolicy.DISCARD_ENTIRE_OBJECT
        )
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = make_processor(VehiclePositionProcessingService, {})
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )

        vehicle_uuid = datasource._make_unique_id("veh-upd-1", "Demo")
        realtime_repository.list_vehicles_for_data_source = AsyncMock(
            return_value=[SimpleNamespace(id=vehicle_uuid, data_source_id=2)]
        )

        records = [
            {
                "id": "veh-upd-1",
                "trip": {
                    "trip_id": "trip-1",
                    "start_time": "08:00:00",
                    "start_date": "20260801",
                    "route_id": "invalid-route",
                },
                "vehicle_id": "vehicle-1",
                "timestamp": "2026-08-01T08:05:00Z",
                "latitude": 47.1,
                "longitude": 8.5,
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
        realtime_repository.update_vehicle_position_from_sync.assert_not_awaited()
        realtime_repository.delete_vehicles_for_data_source_by_ids.assert_awaited()

class TestVehiclePositionTripDescriptorAndMatching(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _record(trip: dict | None = None, **overrides) -> dict:
        record = {
            "id": "veh-upd-1",
            "trip": {
                "trip_id": "external-trip-1",
                "start_time": "08:00:00",
                "start_date": "20260801",
                "route_id": "r1",
                **(trip or {}),
            },
            "vehicle_id": "vehicle-1",
            "timestamp": "2026-08-01T08:05:00Z",
            "latitude": 47.1,
            "longitude": 8.5,
        }
        record.update(overrides)
        return record

    @staticmethod
    async def _run(records, match_result=(None, AssignmentType.NO_MATCH_GENERAL), policy=None, entities=None):
        repository = _SystemRepositoryStub()
        if policy is not None:
            repository.get_data_source_invalid_reference_policy = AsyncMock(return_value=policy)

        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value=entities
            or {"agency": {"a1"}, "route": {"r1"}, "stop": {"s1", "s2"}, "trip": {"nominal-trip"}}
        )
        datasource = make_processor(VehiclePositionProcessingService, {})
        datasource._caching_service = SimpleNamespace(put_trip_id=AsyncMock(), pop_trip_id=AsyncMock())
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=match_result))
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: {
                **entity,
                **({"stop_id": f"mapped-{entity['stop_id']}"} if entity.get("stop_id") else {}),
            },
        )

        await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        return datasource, realtime_repository

    async def test_persists_mapped_scheduled_fields_of_trip_descriptor(self):
        start = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
        end = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
        record = self._record(
            {
                "scheduled_start_stop_id": "s1",
                "scheduled_start_time": start,
                "scheduled_end_stop_id": "s2",
                "scheduled_end_time": end,
            }
        )

        _, realtime_repository = await self._run([record])

        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertEqual(kwargs["trip_scheduled_start_stop_id"], "mapped-s1")
        self.assertEqual(kwargs["trip_scheduled_end_stop_id"], "mapped-s2")
        self.assertEqual(kwargs["trip_scheduled_start_time"], start)
        self.assertEqual(kwargs["trip_scheduled_end_time"], end)

    async def test_scheduled_fields_are_none_when_not_provided_and_invalid_times_are_dropped(self):
        record = self._record({"scheduled_start_time": "2026-08-01T08:00:00Z"})

        _, realtime_repository = await self._run([record])

        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertIsNone(kwargs["trip_scheduled_start_stop_id"])
        self.assertIsNone(kwargs["trip_scheduled_end_stop_id"])
        self.assertIsNone(kwargs["trip_scheduled_start_time"])
        self.assertIsNone(kwargs["trip_scheduled_end_time"])

    async def test_intermediate_stops_and_incomplete_flag_are_passed_to_matching(self):
        stop_time = datetime(2026, 8, 1, 8, 10, tzinfo=timezone.utc)
        record = self._record(
            {
                "is_complete_stop_sequence": False,
                "scheduled_intermediate_stops": [("s1", stop_time), ("s2", "invalid"), "broken"],
            }
        )

        datasource, _ = await self._run([record])

        match_kwargs = datasource._matching_service.match.await_args.kwargs
        self.assertFalse(match_kwargs["is_complete_stop_sequence"])
        self.assertEqual(match_kwargs["scheduled_intermediate_stops"], [("mapped-s1", stop_time)])

    async def test_flat_record_fields_are_used_as_fallback_for_matching(self):
        stop_time = datetime(2026, 8, 1, 8, 10, tzinfo=timezone.utc)
        record = self._record(
            is_complete_stop_sequence=False,
            scheduled_intermediate_stops=[("s1", stop_time)],
        )

        datasource, _ = await self._run([record])

        match_kwargs = datasource._matching_service.match.await_args.kwargs
        self.assertFalse(match_kwargs["is_complete_stop_sequence"])
        self.assertEqual(match_kwargs["scheduled_intermediate_stops"], [("mapped-s1", stop_time)])

    async def test_complete_sequence_is_the_default_for_matching(self):
        datasource, _ = await self._run([self._record()])

        self.assertTrue(datasource._matching_service.match.await_args.kwargs["is_complete_stop_sequence"])

    async def test_new_trip_skips_matching_and_is_valid(self):
        record = self._record({"trip_id": "brand-new", "schedule_relationship": "NEW"})

        datasource, realtime_repository = await self._run([record])

        datasource._matching_service.match.assert_not_awaited()
        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertTrue(kwargs["trip_is_trip_valid"])
        self.assertEqual(kwargs["trip_assignment_type"], "DIRECT_BY_ID")
        self.assertTrue(kwargs["is_active_on_create"])

    async def test_matched_trip_is_valid_and_keeps_original_trip_id(self):
        datasource, realtime_repository = await self._run(
            [self._record()], match_result=("nominal-trip", AssignmentType.MATCHED_BY_START_STOP)
        )

        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertEqual(kwargs["trip_id"], "nominal-trip")
        self.assertEqual(kwargs["trip_original_trip_id"], "external-trip-1")
        self.assertEqual(kwargs["trip_assignment_type"], "MATCHED_BY_START_STOP")
        self.assertTrue(kwargs["trip_is_trip_valid"])
        self.assertTrue(kwargs["is_active_on_create"])

    async def test_cached_match_is_not_written_back_to_cache(self):
        datasource, _ = await self._run(
            [self._record()], match_result=("nominal-trip", AssignmentType.MATCH_BY_CACHED_ID)
        )

        datasource._caching_service.put_trip_id.assert_not_awaited()

    async def test_failed_match_marks_trip_invalid_deactivates_and_does_not_cache(self):
        datasource, realtime_repository = await self._run([self._record()])

        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertFalse(kwargs["trip_is_trip_valid"])
        self.assertTrue(kwargs["trip_is_route_valid"])
        self.assertEqual(kwargs["trip_assignment_type"], "NO_MATCH_GENERAL")
        self.assertEqual(kwargs["trip_original_trip_id"], "external-trip-1")
        self.assertFalse(kwargs["is_active_on_create"])
        datasource._caching_service.put_trip_id.assert_not_awaited()

    async def test_ambiguous_match_is_reported_in_assignment_type(self):
        _, realtime_repository = await self._run(
            [self._record()], match_result=(None, AssignmentType.NO_MATCH_AMBIGUOUS_TRIP)
        )

        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertEqual(kwargs["trip_assignment_type"], "NO_MATCH_AMBIGUOUS_TRIP")

    async def test_invalid_stop_reference_does_not_invalidate_the_trip(self):
        record = self._record({"trip_id": "nominal-trip"}, stop_id="unknown-stop")

        _, realtime_repository = await self._run([record])

        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertTrue(kwargs["trip_is_trip_valid"])
        self.assertTrue(kwargs["trip_is_route_valid"])
        self.assertNotIn("is_valid", kwargs)

    async def test_keep_object_disabled_deactivates_vehicle_with_invalid_route(self):
        record = self._record({"trip_id": "nominal-trip", "route_id": "unknown-route"})

        _, realtime_repository = await self._run([record], policy=InvalidReferencePolicy.KEEP_OBJECT_DISABLED)

        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertFalse(kwargs["is_active_on_create"])
        self.assertFalse(kwargs["trip_is_route_valid"])
        self.assertEqual(kwargs["trip_route_id"], "unknown-route")

    async def test_valid_vehicle_is_active_on_create_unless_record_says_otherwise(self):
        record = self._record({"trip_id": "nominal-trip"}, is_active=False)

        _, realtime_repository = await self._run([record])

        self.assertFalse(realtime_repository.update_vehicle_position_from_sync.await_args.kwargs["is_active_on_create"])

    async def test_vehicle_repository_call_has_no_vehicle_level_assignment_or_validity(self):
        _, realtime_repository = await self._run([self._record({"trip_id": "nominal-trip"})])

        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertNotIn("assignment_type", kwargs)
        self.assertNotIn("is_valid", kwargs)

    async def test_vehicle_sync_never_touches_trip_updates(self):
        _, realtime_repository = await self._run(
            [self._record()], match_result=("nominal-trip", AssignmentType.MATCHED_BY_START_STOP)
        )

        realtime_repository.delete_trips_by_trip_ids.assert_not_awaited()
        realtime_repository.update_trip_update_from_sync.assert_not_awaited()
        realtime_repository.list_trips_by_trip_ids.assert_not_awaited()

    @staticmethod
    def _deletion_processor():
        datasource = make_processor(VehiclePositionProcessingService, {})
        datasource._caching_service = SimpleNamespace(put_trip_id=AsyncMock(), pop_trip_id=AsyncMock())
        datasource._matching_service = SimpleNamespace(
            match=AsyncMock(return_value=(None, AssignmentType.NO_MATCH_GENERAL))
        )
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda entity: entity,
        )
        return datasource

    @staticmethod
    def _vehicle_record(record_id, **overrides):
        record = {
            "id": record_id,
            "trip": {"trip_id": "trip-1", "start_time": "", "start_date": "20260801", "route_id": "r1"},
            "vehicle_id": f"vehicle-{record_id}",
            "timestamp": "2026-08-01T08:05:00Z",
            "latitude": 47.1,
            "longitude": 8.5,
        }
        record.update(overrides)
        return record

    async def _sync_records(self, datasource, realtime_repository, records, is_differential=False):
        repository = _SystemRepositoryStub()
        repository.get_data_source_is_differential_updates = AsyncMock(return_value=is_differential)
        return await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=_GtfsRepositoryStub(),
            source_id=2,
            source_name="Demo",
            records=records,
        )

    async def test_flagged_vehicle_is_deleted_by_id_and_not_persisted(self):
        datasource = self._deletion_processor()
        realtime_repository = _RealtimeRepositoryStub()

        await self._sync_records(
            datasource, realtime_repository, [self._vehicle_record("veh-1", is_deleted=True)]
        )

        realtime_repository.delete_vehicles_for_data_source_by_ids.assert_awaited_once_with(
            2, [datasource._make_unique_id("veh-1", "Demo")]
        )
        realtime_repository.update_vehicle_position_from_sync.assert_not_awaited()

    async def test_flagged_vehicle_without_trip_payload_is_still_deleted(self):
        datasource = self._deletion_processor()
        realtime_repository = _RealtimeRepositoryStub()

        await self._sync_records(
            datasource, realtime_repository, [{"id": "veh-1", "is_deleted": True}]
        )

        realtime_repository.delete_vehicles_for_data_source_by_ids.assert_awaited_once_with(
            2, [datasource._make_unique_id("veh-1", "Demo")]
        )

    async def test_missing_flagged_vehicle_is_ignored_and_other_records_are_processed(self):
        datasource = self._deletion_processor()
        realtime_repository = _RealtimeRepositoryStub()
        realtime_repository.delete_vehicles_for_data_source_by_ids = AsyncMock(return_value=0)

        result = await self._sync_records(
            datasource,
            realtime_repository,
            [
                self._vehicle_record("gone", is_deleted=True),
                self._vehicle_record("veh-2"),
            ],
        )

        realtime_repository.update_vehicle_position_from_sync.assert_awaited_once()
        self.assertEqual(result, {"added": 1, "updated": 0, "deleted": 0})

    async def test_existing_flagged_vehicle_is_deleted_once_and_counted(self):
        datasource = self._deletion_processor()
        realtime_repository = _RealtimeRepositoryStub()
        vehicle_uuid = datasource._make_unique_id("veh-1", "Demo")
        realtime_repository.list_vehicles_for_data_source = AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=vehicle_uuid,
                    data_source_id=2,
                    trip_id="trip-1",
                    trip=SimpleNamespace(original_trip_id="orig-trip"),
                )
            ]
        )

        result = await self._sync_records(
            datasource, realtime_repository, [self._vehicle_record("veh-1", is_deleted=True)]
        )

        realtime_repository.delete_vehicles_for_data_source_by_ids.assert_awaited_once_with(2, [vehicle_uuid])
        datasource._caching_service.pop_trip_id.assert_awaited_once_with("orig-trip")
        self.assertEqual(result["deleted"], 1)

    async def test_vehicle_without_flag_is_not_deleted(self):
        for overrides in ({}, {"is_deleted": False}):
            with self.subTest(overrides=overrides):
                datasource = self._deletion_processor()
                realtime_repository = _RealtimeRepositoryStub()

                await self._sync_records(
                    datasource, realtime_repository, [self._vehicle_record("veh-1", **overrides)]
                )

                realtime_repository.delete_vehicles_for_data_source_by_ids.assert_not_awaited()
                realtime_repository.update_vehicle_position_from_sync.assert_awaited_once()

    async def test_flagged_vehicle_does_not_delete_other_vehicles_in_differential_mode(self):
        datasource = self._deletion_processor()
        realtime_repository = _RealtimeRepositoryStub()
        other_uuid = datasource._make_unique_id("other", "Demo")
        realtime_repository.list_vehicles_for_data_source = AsyncMock(
            return_value=[SimpleNamespace(id=other_uuid, data_source_id=2, trip_id="trip-9", trip=None)]
        )

        await self._sync_records(
            datasource,
            realtime_repository,
            [self._vehicle_record("veh-1", is_deleted=True)],
            is_differential=True,
        )

        realtime_repository.delete_vehicles_for_data_source_by_ids.assert_awaited_once_with(
            2, [datasource._make_unique_id("veh-1", "Demo")]
        )
