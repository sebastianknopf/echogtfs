from __future__ import annotations

import re
import sys
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.enum.gtfsrt import AssignmentType
from echogtfs.services.database.mongo_indexes import (
    SERVICE_ALERTS_COLLECTION,
    TRIP_UPDATES_COLLECTION,
    VEHICLE_POSITIONS_COLLECTION,
)
from echogtfs.services.database.realtime_repository import RealtimeRepository

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class _FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)
        self.modifiers: dict = {}

    def sort(self, sort):
        self.modifiers["sort"] = sort
        return self

    def skip(self, skip):
        self.modifiers["skip"] = skip
        return self

    def limit(self, limit):
        self.modifiers["limit"] = limit
        return self

    async def to_list(self):
        return list(self.docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.cursors: list[_FakeCursor] = []
        self.find_calls: list[tuple] = []
        self.count_documents = AsyncMock(return_value=0)
        self.delete_many = AsyncMock(return_value=SimpleNamespace(deleted_count=0))
        self.update_many = AsyncMock(return_value=SimpleNamespace(modified_count=0))
        self.update_one = AsyncMock()
        self.insert_one = AsyncMock()
        self.find_one_and_update = AsyncMock(return_value=None)
        self.bulk_write = AsyncMock()
        self.aggregate_docs: list = []
        self.pipelines: list = []

    def find(self, filter_, projection=None, **options):
        self.find_calls.append((filter_, projection, options))
        cursor = _FakeCursor(self.docs)
        self.cursors.append(cursor)
        return cursor

    async def aggregate(self, pipeline, **options):
        self.pipelines.append(pipeline)
        return _FakeCursor(self.aggregate_docs)


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _FakeClient:
    def __init__(self):
        self.snapshot_flags: list[bool] = []

    def start_session(self, snapshot=False):
        self.snapshot_flags.append(snapshot)
        return _FakeSession()


def _alert_doc(alert_id=None, **overrides):
    doc = {
        "_id": str(alert_id or uuid.uuid4()),
        "data_source_id": None,
        "cause": "UNKNOWN_CAUSE",
        "effect": "UNKNOWN_EFFECT",
        "severity_level": "INFO",
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
        "translations": [{"language": "de", "header_text": "Hallo", "description_text": None, "url": None}],
        "active_periods": [{"period_type": "IMPACT_PERIOD", "start_time": 10, "end_time": 20}],
        "informed_entities": [{"route_id": "R1", "is_route_valid": False}],
    }
    doc.update(overrides)
    return doc


def _trip_doc(trip_uuid=None, **overrides):
    doc = {
        "_id": str(trip_uuid or uuid.uuid4()),
        "data_source_id": 7,
        "trip_id": "trip-1",
        "original_trip_id": "orig-1",
        "start_time": "10:00:00",
        "start_date": "20260101",
        "route_id": "R1",
        "schedule_relationship": "SCHEDULED",
        "assignment_type": "DIRECT_BY_ID",
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
        "stop_events": [
            {
                "stop_id": "s1",
                "original_stop_id": "s1",
                "stop_sequence": "1",
                "arrival_time": NOW,
                "departure_time": NOW,
            }
        ],
    }
    doc.update(overrides)
    return doc


def _vehicle_doc(vehicle_uuid=None, **overrides):
    doc = {
        "_id": str(vehicle_uuid or uuid.uuid4()),
        "data_source_id": 7,
        "vehicle_id": "veh-1",
        "vehicle_label": "Label",
        "vehicle_wheelchair_accessible": "NO_VALUE",
        "timestamp": NOW,
        "latitude": 47.0,
        "longitude": 8.0,
        "current_status": "IN_TRANSIT_TO",
        "congestion_level": "UNKNOWN_CONGESTION_LEVEL",
        "is_active": True,
        "created_at": NOW,
        "updated_at": NOW,
        "trip": {
            "trip_id": "trip-1",
            "original_trip_id": "orig-1",
            "route_id": "R1",
            "start_date": "20260101",
            "start_time": "10:00:00",
            "schedule_relationship": "SCHEDULED",
            "assignment_type": "DIRECT_BY_ID",
        },
    }
    doc.update(overrides)
    return doc


def _sync_trip_kwargs(**overrides):
    kwargs = dict(
        trip_uuid=uuid.uuid4(),
        source_id=7,
        trip_id="trip-1",
        start_time="10:00:00",
        start_date="20260101",
        route_id="R1",
        schedule_relationship="SCHEDULED",
        assignment_type="DIRECT_BY_ID",
        is_active_on_create=True,
        is_trip_valid=True,
        is_route_valid=True,
        stop_events=[],
    )
    kwargs.update(overrides)
    return kwargs


def _sync_vehicle_kwargs(**overrides):
    kwargs = dict(
        vehicle_uuid=uuid.uuid4(),
        source_id=7,
        trip_id="trip-1",
        trip_original_trip_id="orig-1",
        trip_start_time="10:00:00",
        trip_start_date="20260101",
        trip_route_id="R1",
        trip_schedule_relationship="SCHEDULED",
        trip_assignment_type="DIRECT_BY_ID",
        trip_is_trip_valid=True,
        trip_is_route_valid=True,
        trip_scheduled_start_stop_id="S1",
        trip_scheduled_end_stop_id="S9",
        trip_scheduled_start_time=NOW,
        trip_scheduled_end_time=NOW,
        vehicle_id="veh-1",
        vehicle_label=None,
        vehicle_license_plate=None,
        vehicle_wheelchair_accessible="NO_VALUE",
        timestamp=NOW,
        latitude=47.0,
        longitude=8.0,
        current_stop_sequence=None,
        current_status="IN_TRANSIT_TO",
        congestion_level="UNKNOWN_CONGESTION_LEVEL",
        is_active_on_create=True,
    )
    kwargs.update(overrides)
    return kwargs


class TestRealtimeRepository(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.alerts = _FakeCollection()
        self.trips = _FakeCollection()
        self.vehicles = _FakeCollection()
        self.client = _FakeClient()

        repository = object.__new__(RealtimeRepository)
        repository._client = self.client
        repository._database = {
            SERVICE_ALERTS_COLLECTION: self.alerts,
            TRIP_UPDATES_COLLECTION: self.trips,
            VEHICLE_POSITIONS_COLLECTION: self.vehicles,
        }
        repository._data_source_names = AsyncMock(return_value={7: "Current name"})
        self.repository = repository

    @staticmethod
    def _written_operation(collection: _FakeCollection):
        collection.bulk_write.assert_awaited_once()
        return collection.bulk_write.await_args.args[0][0]

    def test_normalize_informed_entity_payload_sets_per_field_defaults(self):
        payload = RealtimeRepository._normalize_informed_entity_payload(
            {"agency_id": "a1", "route_id": "r1", "stop_id": "s1", "trip_id": None}
        )

        self.assertTrue(payload["is_agency_valid"])
        self.assertTrue(payload["is_route_valid"])
        self.assertTrue(payload["is_stop_valid"])
        self.assertTrue(payload["is_trip_valid"])

    # ------------------------------------------------------------------ alerts

    async def test_delete_alerts_for_data_source_returns_deleted_count(self):
        self.alerts.delete_many.return_value = SimpleNamespace(deleted_count=3)

        result = await self.repository.delete_alerts_for_data_source(7)

        self.assertEqual(result, 3)
        self.alerts.delete_many.assert_awaited_once_with({"data_source_id": 7})

    async def test_get_realtime_service_alerts_reads_active_alerts_from_snapshot(self):
        alert_id = uuid.uuid4()
        self.alerts.docs = [_alert_doc(alert_id)]

        items = await self.repository.get_realtime_service_alerts()

        self.assertEqual([item.id for item in items], [alert_id])
        self.assertEqual(self.client.snapshot_flags, [True])
        filter_, _projection, options = self.alerts.find_calls[0]
        self.assertEqual(filter_, {"is_active": True})
        self.assertIn("session", options)
        self.assertEqual(len(items[0].translations), 1)
        self.assertEqual(items[0].active_periods[0].end_time, 20)
        self.assertFalse(items[0].informed_entities[0].is_route_valid)
        self.assertIs(items[0].informed_entities[0].alert, items[0])

    async def test_list_expired_alert_ids_filters_on_end_time_and_active_flag(self):
        alert_id = uuid.uuid4()
        self.alerts.docs = [{"_id": str(alert_id)}]

        result = await self.repository.list_expired_alert_ids(100, only_active=True)

        self.assertEqual(result, [alert_id])
        self.assertEqual(self.alerts.find_calls[0][0], {"max_end_time": {"$lt": 100}, "is_active": True})

        await self.repository.list_expired_alert_ids(100, only_active=False)
        self.assertEqual(self.alerts.find_calls[1][0], {"max_end_time": {"$lt": 100}})

    async def test_list_alert_ids_expired_before_returns_ids(self):
        alert_id = uuid.uuid4()
        self.alerts.docs = [{"_id": str(alert_id)}]

        result = await self.repository.list_alert_ids_expired_before(50)

        self.assertEqual(result, [alert_id])
        self.assertEqual(self.alerts.find_calls[0][0], {"max_end_time": {"$lt": 50}})

    async def test_deactivate_service_alerts_returns_zero_for_empty_ids(self):
        self.assertEqual(await self.repository.deactivate_service_alerts([]), 0)
        self.alerts.update_many.assert_not_awaited()

    async def test_deactivate_service_alerts_updates_matching_alerts(self):
        alert_id = uuid.uuid4()
        self.alerts.update_many.return_value = SimpleNamespace(modified_count=1)

        result = await self.repository.deactivate_service_alerts([alert_id])

        self.assertEqual(result, 1)
        filter_, update = self.alerts.update_many.await_args.args
        self.assertEqual(filter_, {"_id": {"$in": [str(alert_id)]}})
        self.assertFalse(update["$set"]["is_active"])

    async def test_delete_service_alerts_by_ids_returns_zero_for_empty_ids(self):
        self.assertEqual(await self.repository.delete_service_alerts_by_ids([]), 0)
        self.alerts.delete_many.assert_not_awaited()

    async def test_delete_service_alerts_by_ids_deletes_documents(self):
        alert_id = uuid.uuid4()
        self.alerts.delete_many.return_value = SimpleNamespace(deleted_count=1)

        result = await self.repository.delete_service_alerts_by_ids([alert_id])

        self.assertEqual(result, 1)
        self.alerts.delete_many.assert_awaited_once_with({"_id": {"$in": [str(alert_id)]}})

    async def test_delete_service_alerts_for_data_source_by_ids_is_scoped_to_the_source(self):
        alert_id = uuid.uuid4()

        self.assertEqual(await self.repository.delete_service_alerts_for_data_source_by_ids(7, []), 0)
        await self.repository.delete_service_alerts_for_data_source_by_ids(7, [alert_id])

        self.alerts.delete_many.assert_awaited_once_with({"data_source_id": 7, "_id": {"$in": [str(alert_id)]}})

    async def test_list_service_alerts_paginated_returns_items_total_and_names(self):
        self.alerts.docs = [_alert_doc(data_source_id=7)]
        self.alerts.count_documents.return_value = 11

        items, total = await self.repository.list_service_alerts_paginated(
            page=2, limit=5, sort="oldest", search=" hallo ", is_active=True, has_data_source=True
        )

        self.assertEqual(total, 11)
        self.assertEqual(items[0].data_source_name, "Current name")
        filter_ = self.alerts.find_calls[0][0]
        self.assertEqual(filter_["is_active"], True)
        self.assertEqual(filter_["data_source_id"], {"$ne": None})
        self.assertEqual(filter_["translations.header_text"], {"$regex": "hallo", "$options": "i"})
        modifiers = self.alerts.cursors[0].modifiers
        self.assertEqual(modifiers["skip"], 5)
        self.assertEqual(modifiers["limit"], 5)
        self.assertEqual(modifiers["sort"][1], ("first_start", 1))

    async def test_list_service_alerts_paginated_internal_alerts_filter_on_missing_data_source(self):
        await self.repository.list_service_alerts_paginated(
            page=1, limit=5, sort="newest", search="", is_active=None, has_data_source=False
        )

        self.assertEqual(self.alerts.find_calls[0][0], {"data_source_id": None})

    async def test_get_service_alert_by_id_with_relations_returns_alert_or_none(self):
        alert_id = uuid.uuid4()
        self.assertIsNone(await self.repository.get_service_alert_by_id_with_relations(alert_id))

        self.alerts.docs = [_alert_doc(alert_id)]
        alert = await self.repository.get_service_alert_by_id_with_relations(alert_id)

        self.assertEqual(alert.id, alert_id)
        self.assertEqual(self.alerts.find_calls[1][0], {"_id": str(alert_id)})

    async def test_create_service_alert_inserts_hierarchical_document_with_derived_fields(self):
        alert = await self.repository.create_service_alert(
            cause="CONSTRUCTION",
            effect="DETOUR",
            severity_level="WARNING",
            is_active=True,
            translations=[{"language": "de", "header_text": "Hallo"}],
            active_periods=[
                {"period_type": "IMPACT_PERIOD", "start_time": 30, "end_time": 40},
                {"period_type": "IMPACT_PERIOD", "start_time": 10, "end_time": None},
            ],
            informed_entities=[{"route_id": "R1", "is_route_valid": False}],
        )

        document = self.alerts.insert_one.await_args.args[0]
        self.assertIsNone(document["data_source_id"])
        self.assertEqual(document["first_start"], 10)
        self.assertTrue(document["has_first_start"])
        self.assertEqual(document["max_end_time"], 40)
        self.assertTrue(document["has_invalid_reference"])
        self.assertEqual(alert.cause, "CONSTRUCTION")
        self.assertEqual(alert.translations[0].header_text, "Hallo")

    async def test_update_service_alert_returns_none_when_not_found(self):
        result = await self.repository.update_service_alert(uuid.uuid4(), is_active=False)

        self.assertIsNone(result)
        self.alerts.update_one.assert_not_awaited()

    async def test_update_service_alert_keeps_untouched_children_and_recomputes_derived_fields(self):
        alert_id = uuid.uuid4()
        self.alerts.docs = [_alert_doc(alert_id)]

        result = await self.repository.update_service_alert(
            alert_id,
            cause="STRIKE",
            active_periods=[{"period_type": "IMPACT_PERIOD", "start_time": 100, "end_time": 200}],
        )

        self.assertEqual(result.id, alert_id)
        changes = self.alerts.update_one.await_args.args[1]["$set"]
        self.assertEqual(changes["cause"], "STRIKE")
        self.assertEqual(changes["max_end_time"], 200)
        self.assertEqual(changes["translations"][0]["header_text"], "Hallo")
        self.assertNotIn("is_active", changes)

    async def test_toggle_service_alert_active_returns_none_when_not_found(self):
        self.assertIsNone(await self.repository.toggle_service_alert_active(uuid.uuid4()))

    async def test_toggle_service_alert_active_returns_updated_alert(self):
        alert_id = uuid.uuid4()
        self.alerts.find_one_and_update.return_value = _alert_doc(alert_id, is_active=False, data_source_id=7)

        alert = await self.repository.toggle_service_alert_active(alert_id)

        self.assertFalse(alert.is_active)
        self.assertEqual(alert.data_source_name, "Current name")

    async def test_list_service_alerts_by_ids_returns_empty_for_no_ids(self):
        self.assertEqual(await self.repository.list_service_alerts_by_ids([]), [])
        self.assertEqual(self.alerts.find_calls, [])

    async def test_upsert_service_alert_from_sync_sets_is_active_only_on_insert(self):
        alert_id = uuid.uuid4()

        result = await self.repository.upsert_service_alert_from_sync(
            alert_id=alert_id,
            source_id=7,
            cause="CONSTRUCTION",
            effect="DETOUR",
            severity_level="INFO",
            is_active_on_create=False,
            translations=[],
            active_periods=[],
            informed_entities=[],
        )

        operation = self._written_operation(self.alerts)
        self.assertEqual(result, "upserted")
        self.assertEqual(operation._filter, {"_id": str(alert_id)})
        self.assertTrue(operation._upsert)
        self.assertNotIn("is_active", operation._doc["$set"])
        self.assertEqual(operation._doc["$set"]["data_source_id"], 7)
        self.assertFalse(operation._doc["$setOnInsert"]["is_active"])
        self.assertNotIn("source", operation._doc["$set"])

    # ------------------------------------------------------------------ trip updates

    async def test_get_realtime_trips_reads_snapshot_and_attaches_vehicles(self):
        self.trips.docs = [_trip_doc()]
        self.vehicles.docs = [_vehicle_doc()]

        items = await self.repository.get_realtime_trips()

        self.assertEqual(self.client.snapshot_flags, [True])
        self.assertEqual(self.trips.find_calls[0][0], {"is_active": True})
        self.assertIn("session", self.trips.find_calls[0][2])
        self.assertIn("session", self.vehicles.find_calls[0][2])
        self.assertEqual(items[0].vehicle.vehicle_id, "veh-1")
        self.assertEqual(items[0].data_source_name, "Current name")
        self.assertEqual(items[0].stop_events[0].stop_id, "s1")
        self.assertIs(items[0].stop_events[0].trip, items[0])

    async def test_get_realtime_trips_returns_empty_list(self):
        self.assertEqual(await self.repository.get_realtime_trips(), [])

    async def test_list_trips_paginated_only_returns_trips_with_stop_events(self):
        self.trips.docs = [_trip_doc()]
        self.trips.count_documents.return_value = 1

        items, total = await self.repository.list_trips_paginated(
            page=1, limit=10, sort="desc", search="", is_active=False
        )

        self.assertEqual((len(items), total), (1, 1))
        filter_ = self.trips.find_calls[0][0]
        self.assertEqual(filter_["stop_event_count"], {"$gt": 0})
        self.assertFalse(filter_["is_active"])
        self.assertEqual(self.trips.cursors[0].modifiers["sort"][0], ("start_date", -1))

    async def test_list_trip_ids_with_invalid_stop_events_uses_flag(self):
        self.assertEqual(await self.repository.list_trip_ids_with_invalid_stop_events([]), set())

        self.trips.docs = [{"trip_id": "trip-1"}]
        result = await self.repository.list_trip_ids_with_invalid_stop_events(["trip-1", "trip-2"])

        self.assertEqual(result, {"trip-1"})
        self.assertEqual(self.trips.find_calls[0][0], {"trip_id": {"$in": ["trip-1", "trip-2"]}, "flags": "invalid_stop"})

    async def test_toggle_trip_active_returns_none_when_not_found(self):
        self.assertIsNone(await self.repository.toggle_trip_active(uuid.uuid4()))

    async def test_toggle_trip_active_returns_trip_with_vehicle(self):
        self.trips.find_one_and_update.return_value = _trip_doc(is_active=False)
        self.vehicles.docs = [_vehicle_doc()]

        trip = await self.repository.toggle_trip_active(uuid.uuid4())

        self.assertFalse(trip.is_active)
        self.assertEqual(trip.vehicle.vehicle_id, "veh-1")

    async def test_delete_trips_for_data_source_returns_deleted_count(self):
        self.trips.delete_many.return_value = SimpleNamespace(deleted_count=4)

        self.assertEqual(await self.repository.delete_trips_for_data_source(7), 4)
        self.trips.delete_many.assert_awaited_once_with({"data_source_id": 7})

    async def test_update_trip_update_from_sync_embeds_sorted_stop_events_and_flags(self):
        trip_uuid = uuid.uuid4()
        early = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)

        await self.repository.update_trip_update_from_sync(
            **_sync_trip_kwargs(
                trip_uuid=trip_uuid,
                original_trip_id="orig-1",
                is_complete_stop_sequence=False,
                stop_events=[
                    {"stop_id": "s2", "stop_sequence": 10, "arrival_time": NOW, "departure_time": NOW},
                    {
                        "stop_id": "s1",
                        "original_stop_id": "x1",
                        "stop_sequence": 2,
                        "arrival_time": NOW,
                        "departure_time": early,
                        "is_valid": False,
                    },
                ],
            )
        )

        operation = self._written_operation(self.trips)
        fields = operation._doc["$set"]
        self.assertEqual(
            operation._filter,
            {"$or": [{"_id": str(trip_uuid)}, {"trip_id": "trip-1"}]},
        )
        self.assertEqual(operation._doc["$setOnInsert"]["_id"], str(trip_uuid))
        self.assertEqual([event["stop_sequence"] for event in fields["stop_events"]], ["2", "10"])
        self.assertEqual(fields["stop_event_count"], 2)
        self.assertEqual(fields["original_trip_id"], "orig-1")
        self.assertFalse(fields["is_complete_stop_sequence"])
        self.assertTrue(
            {"invalid_stop", "changed_stop_id", "departure_before_arrival", "realtime"} <= set(fields["flags"])
        )
        self.assertNotIn("is_active", fields)
        self.assertTrue(operation._doc["$setOnInsert"]["is_active"])

    async def test_update_trip_update_from_sync_flags_invalid_references(self):
        await self.repository.update_trip_update_from_sync(**_sync_trip_kwargs(is_route_valid=False))

        flags = self._written_operation(self.trips)._doc["$set"]["flags"]
        self.assertEqual(flags, ["invalid_reference"])

    async def test_update_trip_update_from_sync_never_overwrites_assignment_with_cached_id(self):
        await self.repository.update_trip_update_from_sync(
            **_sync_trip_kwargs(assignment_type=AssignmentType.MATCH_BY_CACHED_ID)
        )

        operation = self._written_operation(self.trips)
        self.assertNotIn("assignment_type", operation._doc["$set"])
        self.assertEqual(operation._doc["$setOnInsert"]["assignment_type"], AssignmentType.MATCH_BY_CACHED_ID.value)

    # ------------------------------------------------------------------ vehicle positions

    async def test_get_realtime_vehicles_reads_active_vehicles_from_snapshot(self):
        self.vehicles.docs = [_vehicle_doc()]

        items = await self.repository.get_realtime_vehicles()

        self.assertEqual(self.client.snapshot_flags, [True])
        self.assertEqual(self.vehicles.find_calls[0][0], {"is_active": True})
        self.assertEqual(items[0].trip_id, "trip-1")
        self.assertEqual(items[0].trip.original_trip_id, "orig-1")
        self.assertTrue(items[0].trip.is_valid)

    async def test_get_realtime_vehicles_returns_empty_list(self):
        self.assertEqual(await self.repository.get_realtime_vehicles(), [])

    async def test_list_vehicles_paginated_returns_items_total_and_names(self):
        self.vehicles.docs = [_vehicle_doc()]
        self.vehicles.count_documents.return_value = 3

        items, total = await self.repository.list_vehicles_paginated(page=1, limit=10, search="veh", is_active=True)

        self.assertEqual(total, 3)
        self.assertEqual(items[0].data_source_name, "Current name")
        filter_ = self.vehicles.find_calls[0][0]
        self.assertTrue(filter_["is_active"])
        self.assertIn({"trip.trip_id": {"$regex": "veh", "$options": "i"}}, filter_["$or"])

    async def test_toggle_vehicle_active_returns_none_when_not_found(self):
        self.assertIsNone(await self.repository.toggle_vehicle_active(uuid.uuid4()))

    async def test_toggle_vehicle_active_returns_updated_vehicle(self):
        self.vehicles.find_one_and_update.return_value = _vehicle_doc(is_active=False)

        vehicle = await self.repository.toggle_vehicle_active(uuid.uuid4())

        self.assertFalse(vehicle.is_active)
        self.assertEqual(vehicle.data_source_name, "Current name")

    async def test_delete_vehicles_for_data_source_returns_deleted_count(self):
        self.vehicles.delete_many.return_value = SimpleNamespace(deleted_count=2)

        self.assertEqual(await self.repository.delete_vehicles_for_data_source(7), 2)
        self.vehicles.delete_many.assert_awaited_once_with({"data_source_id": 7})

    async def test_update_vehicle_position_from_sync_embeds_trip_descriptor_and_keeps_is_active(self):
        vehicle_uuid = uuid.uuid4()

        await self.repository.update_vehicle_position_from_sync(
            **_sync_vehicle_kwargs(vehicle_uuid=vehicle_uuid, is_active_on_create=False, trip_is_route_valid=False)
        )

        operation = self._written_operation(self.vehicles)
        fields = operation._doc["$set"]
        self.assertEqual(
            operation._filter,
            {"$or": [{"_id": str(vehicle_uuid)}, {"trip.trip_id": "trip-1"}]},
        )
        self.assertTrue(operation._upsert)
        self.assertNotIn("is_active", fields)
        self.assertFalse(operation._doc["$setOnInsert"]["is_active"])
        self.assertEqual(fields["trip.trip_id"], "trip-1")
        self.assertEqual(fields["trip.original_trip_id"], "orig-1")
        self.assertEqual(fields["trip.scheduled_start_stop_id"], "S1")
        self.assertEqual(fields["trip.scheduled_end_stop_id"], "S9")
        self.assertNotIn("assignment_type", fields)
        self.assertNotIn("is_valid", fields)
        self.assertEqual(fields["trip.assignment_type"], "DIRECT_BY_ID")
        self.assertTrue(fields["trip.is_trip_valid"])
        self.assertFalse(fields["trip.is_route_valid"])

    async def test_update_vehicle_position_from_sync_never_overwrites_assignment_with_cached_id(self):
        await self.repository.update_vehicle_position_from_sync(
            **_sync_vehicle_kwargs(
                trip_assignment_type=AssignmentType.MATCH_BY_CACHED_ID,
            )
        )

        operation = self._written_operation(self.vehicles)
        cached = AssignmentType.MATCH_BY_CACHED_ID.value
        self.assertNotIn("trip.assignment_type", operation._doc["$set"])
        self.assertEqual(operation._doc["$setOnInsert"]["trip.assignment_type"], cached)

    # ------------------------------------------------------------------ dashboard and statistics

    async def test_count_methods_use_active_flags(self):
        self.alerts.count_documents.side_effect = [4, 1]
        self.vehicles.count_documents.side_effect = [6, 2]
        self.trips.count_documents.side_effect = [3, 5, 7]

        self.assertEqual(await self.repository.count_service_alerts_by_active(), (4, 1))
        self.assertEqual(await self.repository.count_vehicle_positions_by_active(), (6, 2))
        self.assertEqual(await self.repository.count_trip_updates_by_status(), (3, 5, 7))

    async def test_list_realtime_object_statistics_returns_counts_per_route(self):
        self.alerts.count_documents.return_value = 7
        self.repository._list_running_gtfs_trips = AsyncMock(return_value={"t1": "R1", "t2": "R1", "t3": "R2"})
        self.trips.aggregate_docs = [
            {
                "trip_id": "t1",
                "assignment_type": "DIRECT_BY_ID",
                "stop_event_count": 3,
                "num_non_no_data_events": 3,
                "num_realtime_events": 2,
            },
            {
                "trip_id": "t2",
                "assignment_type": "NO_MATCH_GENERAL",
                "stop_event_count": 2,
                "num_non_no_data_events": 0,
                "num_realtime_events": 0,
            },
            {"trip_id": "t3", "assignment_type": "MATCH_BY_CACHED_ID", "stop_event_count": 0},
        ]
        self.vehicles.docs = [
            {"trip": {"trip_id": "t1", "assignment_type": "DIRECT_BY_ID"}},
            {"trip": {"trip_id": "t3", "assignment_type": "NO_MATCH_AMBIGUOUS_TRIP"}},
        ]

        result = await self.repository.list_realtime_object_statistics(["R1", "R2", "R3"])

        self.assertEqual(result["num_alerts"], 7)
        r1 = result["trips"]["R1"]
        self.assertEqual((r1["num_running_trips"], r1["num_realtime_trips"], r1["num_monitored_trips"]), (2, 1, 1))
        self.assertIn({"DIRECT_BY_ID": 1}, r1["assignment_types"])
        self.assertIn({"NO_MATCH_GENERAL": 1}, r1["assignment_types"])
        self.assertNotIn("MATCH_BY_CACHED_ID", [key for item in r1["assignment_types"] for key in item])
        self.assertEqual(result["trips"]["R2"]["num_monitored_trips"], 0)
        self.assertEqual(result["trips"]["R3"]["num_running_trips"], 0)
        self.assertEqual(result["vehicles"]["R1"]["num_vehicles"], 1)
        self.assertEqual(result["vehicles"]["R2"]["num_vehicles"], 1)
        self.assertIn({"NO_MATCH_AMBIGUOUS_TRIP": 1}, result["vehicles"]["R2"]["assignment_types"])
        self.assertEqual(result["vehicles"]["R3"]["num_vehicles"], 0)

        trip_pipeline = self.trips.pipelines[0]
        self.assertEqual(trip_pipeline[0]["$match"]["trip_id"], {"$in": ["t1", "t2", "t3"]})

    async def test_list_realtime_object_statistics_without_routes_skips_trip_queries(self):
        self.repository._list_running_gtfs_trips = AsyncMock()

        result = await self.repository.list_realtime_object_statistics([])

        self.assertEqual(result, {"num_alerts": 0, "trips": {}, "vehicles": {}})
        self.repository._list_running_gtfs_trips.assert_not_awaited()

    # ------------------------------------------------------------------ conflict queries

    async def test_list_informed_entities_with_invalid_references_matches_all_validity_flags(self):
        alert_id = uuid.uuid4()
        self.alerts.aggregate_docs = [
            {**_alert_doc(alert_id), "informed_entities": {"route_id": "R1", "is_route_valid": False}, "entity_index": 0}
        ]

        result = await self.repository.list_informed_entities_with_invalid_references()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].alert.id, alert_id)
        self.assertFalse(result[0].is_route_valid)
        pipeline = self.alerts.pipelines[0]
        self.assertEqual(pipeline[0], {"$match": {"has_invalid_reference": True}})
        self.assertEqual(
            {key for condition in pipeline[-1]["$match"]["$or"] for key in condition},
            {
                "informed_entities.is_agency_valid",
                "informed_entities.is_route_valid",
                "informed_entities.is_stop_valid",
                "informed_entities.is_trip_valid",
            },
        )

    async def test_list_informed_entities_with_non_global_ids_uses_pattern_for_all_reference_fields(self):
        pattern = r"^[A-Z0-9]{3}:[A-Z0-9]{3}:\d+$"

        await self.repository.list_informed_entities_with_non_global_ids(pattern)

        conditions = self.alerts.pipelines[0][-1]["$match"]["$or"]
        self.assertEqual(
            {key for condition in conditions for key in condition},
            {
                "informed_entities.agency_id",
                "informed_entities.route_id",
                "informed_entities.stop_id",
                "informed_entities.trip_id",
            },
        )
        for condition in conditions:
            self.assertEqual(next(iter(condition.values()))["$not"], re.compile(pattern))

    async def test_list_stop_events_with_non_global_ids_returns_events_with_parent_trip(self):
        pattern = r"^[A-Z0-9]{3}:[A-Z0-9]{3}:\d+$"
        trip_uuid = uuid.uuid4()
        self.trips.aggregate_docs = [
            {**_trip_doc(trip_uuid), "stop_events": {"stop_id": "bad", "original_stop_id": "bad", "stop_sequence": "1"}}
        ]

        result = await self.repository.list_stop_events_with_non_global_ids(pattern)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].stop_id, "bad")
        self.assertEqual(result[0].trip.id, trip_uuid)
        self.assertEqual(result[0].trip.data_source_name, "Current name")
        self.assertEqual(self.trips.pipelines[0][-1]["$match"]["stop_events.stop_id"]["$not"], re.compile(pattern))

    async def test_list_trips_with_non_global_ids_returns_trips_without_stop_events(self):
        pattern = r"^[A-Z0-9]{3}:[A-Z0-9]{3}:\d+$"
        self.trips.docs = [_trip_doc(trip_id="invalid-trip")]

        result = await self.repository.list_trips_with_non_global_ids(pattern)

        self.assertEqual([trip.trip_id for trip in result], ["invalid-trip"])
        self.assertEqual(result[0].stop_events, [])
        filter_, projection, _options = self.trips.find_calls[0]
        self.assertEqual({key for condition in filter_["$or"] for key in condition}, {"trip_id", "route_id"})
        self.assertEqual(projection, {"stop_events": 0})


if __name__ == "__main__":
    unittest.main()
