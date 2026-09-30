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
from _realtime_processing_test_support import _SystemRepositoryStub, _RealtimeRepositoryStub, _GtfsRepositoryStub, make_processor
from echogtfs.services.realtime_processing.vehicle_position_processing_service import VehiclePositionProcessingService

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
        self.assertEqual(kwargs["assignment_type"], "DIRECT_BY_ID")
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
        self.assertEqual(kwargs["assignment_type"], "NO_MATCH_GENERAL")
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
        realtime_repository.delete_trips_by_trip_ids.assert_awaited_once_with(["external-trip-1"])
        match_kwargs = datasource._matching_service.match.await_args.kwargs
        self.assertIsNotNone(match_kwargs["scheduled_start_time"])
        self.assertIsNotNone(match_kwargs["scheduled_end_time"])
        self.assertEqual(match_kwargs["scheduled_start_stop_id"], "s1")
        self.assertEqual(match_kwargs["scheduled_end_stop_id"], "s1")
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
        self.assertFalse(kwargs["is_valid"])
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
