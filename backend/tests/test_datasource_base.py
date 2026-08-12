from __future__ import annotations

from datetime import datetime, timezone
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")

from echogtfs.datasources.base import DatasourceBase
from echogtfs.enum.system import InvalidReferencePolicy


class _TestDatasource(DatasourceBase):
    def _validate_config(self) -> None:
        return None

    async def _fetch_records(self):
        return self.config.get("_payload", {"record_type": "service_alerts", "records": []})


class _SystemRepositoryStub:
    def __init__(self):
        self.get_data_source_invalid_reference_policy = AsyncMock(
            return_value=InvalidReferencePolicy.DISCARD_INVALID
        )
        self.list_data_source_mappings_grouped = AsyncMock(return_value={})
        self.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"trip-1"}}
        )


class _RealtimeRepositoryStub:
    def __init__(self):
        self.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"trip-1"}}
        )
        self.list_service_alerts_for_data_source = AsyncMock(return_value=[])
        self.list_service_alerts_by_ids = AsyncMock(return_value=[])
        self.delete_service_alerts_for_data_source_by_ids = AsyncMock()
        self.delete_service_alerts_by_ids = AsyncMock()
        self.upsert_service_alert_from_sync = AsyncMock()
        self.list_trips_for_data_source = AsyncMock(return_value=[])
        self.list_trips_by_ids = AsyncMock(return_value=[])
        self.list_trips_by_trip_ids = AsyncMock(return_value=[])
        self.list_trip_ids_with_stop_events = AsyncMock(return_value=set())
        self.delete_trips_for_data_source_by_ids = AsyncMock()
        self.update_trip_update_from_sync = AsyncMock()
        self.list_vehicles_for_data_source = AsyncMock(return_value=[])
        self.list_vehicles_by_ids = AsyncMock(return_value=[])
        self.delete_vehicles_for_data_source_by_ids = AsyncMock()
        self.update_vehicle_position_from_sync = AsyncMock()


class _GtfsRepositoryStub:
    def __init__(self):
        self.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"trip-1"}}
        )
        self.get_gtfs_trip_with_stop_times = AsyncMock(return_value=None)


class TestDatasourceBaseHelpers(unittest.TestCase):
    def setUp(self):
        self.datasource = _TestDatasource({})

    def test_make_unique_id_is_deterministic_for_non_uuid(self):
        value_a = self.datasource._make_unique_id("alert-1", "src")
        value_b = self.datasource._make_unique_id("alert-1", "src")
        self.assertEqual(value_a, value_b)

    def test_make_unique_id_keeps_uuid(self):
        original = "f5d3f5ec-f6ca-4d16-9330-f6691a53b4c8"
        self.assertEqual(str(self.datasource._make_unique_id(original, "src")), original)

    def test_normalize_payload_accepts_envelope(self):
        record_type, records = self.datasource._normalize_fetched_payload(
            {"record_type": "service_alerts", "records": [{"id": 1}]}
        )
        self.assertEqual(record_type, "service_alerts")
        self.assertEqual(records, [{"id": 1}])

    def test_normalize_payload_rejects_invalid_shape(self):
        with self.assertRaises(ValueError):
            self.datasource._normalize_fetched_payload({"records": []})

    def test_validate_entity_rejects_trip_only(self):
        is_valid = self.datasource._validate_entity(
            {"trip_id": "T1", "agency_id": None, "route_id": None, "stop_id": None},
            {"agency": set(), "route": set(), "stop": set()},
        )
        self.assertFalse(is_valid)

    def test_validate_and_clean_entity_elements_removes_invalid_fields(self):
        cleaned, has_valid = self.datasource._validate_and_clean_entity_elements(
            {"agency_id": "unknown", "route_id": "r1", "stop_id": "s9"},
            {"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}},
        )
        self.assertTrue(has_valid)
        self.assertIsNone(cleaned["agency_id"])
        self.assertEqual(cleaned["route_id"], "r1")
        self.assertIsNone(cleaned["stop_id"])

    def test_deduplicate_entities(self):
        entities = [
            {
                "agency_id": "a1",
                "route_id": "r1",
                "route_type": None,
                "stop_id": None,
                "trip_id": None,
                "direction_id": None,
            },
            {
                "agency_id": "a1",
                "route_id": "r1",
                "route_type": None,
                "stop_id": None,
                "trip_id": None,
                "direction_id": None,
            },
        ]
        self.assertEqual(len(self.datasource._deduplicate_entities(entities)), 1)

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
        self.assertEqual(propagated[0]["stop_id"], "de:1:2:3")

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


class TestDatasourceBaseDeepSync(unittest.IsolatedAsyncioTestCase):
    async def test_sync_records_logs_runtime_steps(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = _TestDatasource({})

        async def fake_fetch_records():
            return {"record_type": "service_alerts", "records": []}

        async def fake_sync_service_alerts(**kwargs):
            return {"added": 0, "updated": 0, "deleted": 0}

        datasource._fetch_records = fake_fetch_records
        datasource._sync_service_alert_records = fake_sync_service_alerts

        with self.assertLogs("uvicorn", level="INFO") as captured:
            result = await datasource.sync_records(
                repository=repository,
                realtime_repository=realtime_repository,
                gtfs_repository=gtfs_repository,
                source_id=2,
                source_name="Demo",
                log_dumps=False,
            )

        self.assertEqual(result, {"added": 0, "updated": 0, "deleted": 0})
        logs = "\n".join(captured.output)
        self.assertIn("datasource run", logs.lower())
        self.assertIn("extract", logs.lower())
        self.assertIn("transform", logs.lower())
        self.assertIn("load", logs.lower())

    async def test_sync_records_uses_transformer_runtime_from_payload(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = _TestDatasource({})

        async def fake_fetch_records():
            return {
                "record_type": "service_alerts",
                "records": [],
                "_transform_runtime_ms": 42.5,
            }

        async def fake_sync_service_alerts(**kwargs):
            return {"added": 0, "updated": 0, "deleted": 0}

        datasource._fetch_records = fake_fetch_records
        datasource._sync_service_alert_records = fake_sync_service_alerts

        with self.assertLogs("uvicorn", level="INFO") as captured:
            await datasource.sync_records(
                repository=repository,
                realtime_repository=realtime_repository,
                gtfs_repository=gtfs_repository,
                source_id=2,
                source_name="Demo",
                log_dumps=False,
            )

        logs = "\n".join(captured.output)
        self.assertIn("transform=42.50ms", logs)

    async def test_sync_service_alert_records_applies_policy_and_upserts(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = _TestDatasource({})
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda e: e,
        )
        datasource._entity_enrichment_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_enrichment_count=lambda: 0,
            apply_enrichment=lambda _a, _b: None,
        )

        records = [
            {
                "id": "alert-1",
                "cause": "UNKNOWN_CAUSE",
                "effect": "UNKNOWN_EFFECT",
                "severity_level": "UNKNOWN_SEVERITY",
                "is_active": True,
                "translations": [],
                "active_periods": [],
                "informed_entities": [{"agency_id": "x", "route_id": None, "stop_id": None}],
            }
        ]

        result = await datasource._sync_service_alert_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        self.assertEqual(result, {"added": 1, "updated": 0, "deleted": 0})
        realtime_repository.upsert_service_alert_from_sync.assert_awaited_once()
        kwargs = realtime_repository.upsert_service_alert_from_sync.await_args.kwargs
        self.assertEqual(kwargs["alert_id"], "alert-1")
        self.assertFalse(kwargs["is_active_on_create"])
        self.assertEqual(kwargs["informed_entities"], [])

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
        datasource = _TestDatasource({})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        result = await datasource._sync_trip_update_records(
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
        datasource = _TestDatasource({})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        result = await datasource._sync_vehicle_position_records(
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

    async def test_sync_trip_update_records_calls_matching_for_non_nominal_trip(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"nominal-trip"}}
        )
        datasource = _TestDatasource({})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value="matched-trip-1"))
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

        result = await datasource._sync_trip_update_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        self.assertEqual(result, {"added": 1, "updated": 0, "deleted": 0})
        datasource._matching_service.match.assert_awaited_once()
        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertEqual(kwargs["trip_id"], "matched-trip-1")
        self.assertEqual(kwargs["assignment_type"], "MATCHED_BY_START_STOP")

    async def test_sync_vehicle_position_records_sets_no_match_assignment_when_matching_fails(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        gtfs_repository.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"nominal-trip"}}
        )
        datasource = _TestDatasource({})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        result = await datasource._sync_vehicle_position_records(
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
        datasource = _TestDatasource({})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        result = await datasource._sync_vehicle_position_records(
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
        datasource = _TestDatasource({})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value="matched-trip-1"))
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

        await datasource._sync_vehicle_position_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        datasource._matching_service.match.assert_awaited_once()
        match_kwargs = datasource._matching_service.match.await_args.kwargs
        self.assertIsNotNone(match_kwargs["scheduled_start_time"])
        self.assertIsNotNone(match_kwargs["scheduled_end_time"])
        self.assertEqual(match_kwargs["scheduled_start_stop_id"], "s1")
        self.assertEqual(match_kwargs["scheduled_end_stop_id"], "s1")

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
        datasource = _TestDatasource({})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        await datasource._sync_trip_update_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        kwargs = realtime_repository.update_trip_update_from_sync.await_args.kwargs
        self.assertFalse(kwargs["is_valid"])
        self.assertFalse(kwargs["is_active_on_create"])
        self.assertEqual(kwargs["assignment_type"], "NO_MATCH_GENERAL")

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
        datasource = _TestDatasource({})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        await datasource._sync_vehicle_position_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        kwargs = realtime_repository.update_vehicle_position_from_sync.await_args.kwargs
        self.assertFalse(kwargs["is_valid"])
        self.assertFalse(kwargs["trip_is_valid"])
        self.assertEqual(kwargs["trip_route_id"], "")

    async def test_sync_trip_update_records_discards_entire_object_and_deletes_existing_when_policy_requires(self):
        repository = _SystemRepositoryStub()
        repository.get_data_source_invalid_reference_policy = AsyncMock(
            return_value=InvalidReferencePolicy.DISCARD_ENTIRE_OBJECT
        )
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = _TestDatasource({})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        result = await datasource._sync_trip_update_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        self.assertEqual(result, {"added": 0, "updated": 0, "deleted": 2})
        realtime_repository.update_trip_update_from_sync.assert_not_awaited()
        realtime_repository.delete_trips_for_data_source_by_ids.assert_awaited()

    async def test_sync_vehicle_position_records_discards_entire_object_and_deletes_existing_when_policy_requires(self):
        repository = _SystemRepositoryStub()
        repository.get_data_source_invalid_reference_policy = AsyncMock(
            return_value=InvalidReferencePolicy.DISCARD_ENTIRE_OBJECT
        )
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = _TestDatasource({})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        result = await datasource._sync_vehicle_position_records(
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

    async def test_sync_records_dispatches_trip_updates_record_type(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = _TestDatasource(
            {
                "_payload": {
                    "record_type": "trip_updates",
                    "records": [
                        {
                            "id": "trip-upd-1",
                            "trip_id": "trip-1",
                            "start_time": "08:00:00",
                            "start_date": "20260801",
                            "route_id": "r1",
                            "stop_events": [],
                        }
                    ],
                }
            }
        )
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))

        result = await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            log_dumps=False,
        )

        self.assertEqual(result, {"added": 1, "updated": 0, "deleted": 0})
        realtime_repository.update_trip_update_from_sync.assert_awaited_once()

    async def test_sync_records_dispatches_vehicle_positions_record_type(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = _TestDatasource(
            {
                "_payload": {
                    "record_type": "vehicle_positions",
                    "records": [
                        {
                            "id": "veh-upd-1",
                            "trip": {
                                "trip_id": "trip-1",
                                "start_time": "08:00:00",
                                "start_date": "20260801",
                                "route_id": "r1",
                            },
                            "vehicle_id": "vehicle-1",
                            "timestamp": "2026-08-01T08:05:00Z",
                            "latitude": 47.1,
                            "longitude": 8.5,
                        }
                    ],
                }
            }
        )
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))

        result = await datasource.sync_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            log_dumps=False,
        )

        self.assertEqual(result, {"added": 1, "updated": 0, "deleted": 0})
        realtime_repository.update_vehicle_position_from_sync.assert_awaited_once()

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
        datasource = _TestDatasource({"treat_unexpected_stop_as_added_stop": True})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        await datasource._sync_trip_update_records(
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
        datasource = _TestDatasource({"treat_missing_stop_as_canceled_stop": True})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        await datasource._sync_trip_update_records(
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
        datasource = _TestDatasource({})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        await datasource._sync_trip_update_records(
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
        datasource = _TestDatasource({"treat_missing_stop_as_canceled_stop": True})
        datasource._matching_service = SimpleNamespace(match=AsyncMock(return_value=None))
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

        await datasource._sync_trip_update_records(
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