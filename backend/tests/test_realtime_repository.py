from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.database.realtime_repository import RealtimeRepository


class _FakeResult:
    def __init__(
        self,
        items=None,
        *,
        rows=None,
        rowcount=None,
        scalar_one_value=None,
        scalar_one_or_none_value=None,
    ):
        self._items = [] if items is None else list(items)
        self._rows = rows
        self.rowcount = rowcount
        self._scalar_one_value = scalar_one_value
        self._scalar_one_or_none_value = scalar_one_or_none_value

    def scalars(self):
        return self

    def all(self):
        if self._rows is not None:
            return list(self._rows)
        return list(self._items)

    def scalar_one(self):
        return self._scalar_one_value

    def scalar_one_or_none(self):
        return self._scalar_one_or_none_value


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestRealtimeRepository(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _make_repository(session):
        repository = object.__new__(RealtimeRepository)
        repository.get_session = lambda: _FakeSessionContext(session)
        return repository

    async def test_delete_alerts_for_data_source_returns_rowcount(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(rowcount=3)),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.delete_alerts_for_data_source(7)

        self.assertEqual(result, 3)
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_update_service_alert_source_name_commits(self):
        session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
        repository = self._make_repository(session)

        await repository.update_service_alert_source_name("old", "new")

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_get_realtime_service_alerts_returns_loaded_alerts(self):
        alert = SimpleNamespace(id="a1")
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult([alert])))
        repository = self._make_repository(session)

        items = await repository.get_realtime_service_alerts()

        self.assertEqual(items, [alert])
        session.execute.assert_awaited_once()

    async def test_list_expired_internal_alert_ids_returns_ids(self):
        alert_id = uuid.uuid4()
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult(rows=[(alert_id,)])))
        repository = self._make_repository(session)

        result = await repository.list_expired_internal_alert_ids(12345, only_active=True)

        self.assertEqual(result, [alert_id])
        session.execute.assert_awaited_once()

    async def test_list_internal_alert_ids_expired_before_returns_ids(self):
        alert_id = uuid.uuid4()
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult(rows=[(alert_id,)])))
        repository = self._make_repository(session)

        result = await repository.list_internal_alert_ids_expired_before(12345)

        self.assertEqual(result, [alert_id])
        session.execute.assert_awaited_once()

    async def test_deactivate_service_alerts_returns_zero_for_empty_ids(self):
        session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
        repository = self._make_repository(session)

        result = await repository.deactivate_service_alerts([])

        self.assertEqual(result, 0)
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_deactivate_service_alerts_updates_and_commits(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(rowcount=2)),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)
        alert_id = uuid.uuid4()

        result = await repository.deactivate_service_alerts([alert_id])

        self.assertEqual(result, 2)
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_delete_service_alerts_by_ids_returns_zero_for_empty_ids(self):
        session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
        repository = self._make_repository(session)

        result = await repository.delete_service_alerts_by_ids([])

        self.assertEqual(result, 0)
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_delete_service_alerts_by_ids_deletes_and_commits(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(rowcount=4)),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.delete_service_alerts_by_ids([uuid.uuid4()])

        self.assertEqual(result, 4)
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_list_service_alerts_for_data_source_returns_alerts(self):
        alert = SimpleNamespace(id="a1")
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult([alert])))
        repository = self._make_repository(session)

        result = await repository.list_service_alerts_for_data_source(1)

        self.assertEqual(result, [alert])
        session.execute.assert_awaited_once()

    async def test_list_service_alerts_paginated_returns_items_and_total(self):
        alert = SimpleNamespace(id="a1")
        session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    _FakeResult(scalar_one_value=9),
                    _FakeResult([alert]),
                ]
            )
        )
        repository = self._make_repository(session)

        items, total = await repository.list_service_alerts_paginated(
            page=1,
            limit=20,
            sort="newest",
            search="",
            is_active=None,
            has_data_source=None,
        )

        self.assertEqual(items, [alert])
        self.assertEqual(total, 9)
        self.assertEqual(session.execute.await_count, 2)

    async def test_get_service_alert_by_id_with_relations_returns_alert_or_none(self):
        alert = SimpleNamespace(id=uuid.uuid4())
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(scalar_one_or_none_value=alert))
        )
        repository = self._make_repository(session)

        result = await repository.get_service_alert_by_id_with_relations(alert.id)

        self.assertEqual(result, alert)
        session.execute.assert_awaited_once()

    async def test_create_service_alert_returns_created_alert(self):
        created_alert = SimpleNamespace(id=uuid.uuid4())
        session = SimpleNamespace(
            add=lambda _: None,
            flush=AsyncMock(),
            execute=AsyncMock(return_value=_FakeResult(scalar_one_value=created_alert)),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.create_service_alert(
            cause="UNKNOWN_CAUSE",
            effect="UNKNOWN_EFFECT",
            severity_level="UNKNOWN_SEVERITY",
            is_active=True,
            translations=[],
            active_periods=[],
            informed_entities=[],
        )

        self.assertEqual(result, created_alert)
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.execute.assert_awaited_once()

    async def test_update_service_alert_returns_none_when_not_found(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(scalar_one_or_none_value=None)),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.update_service_alert(uuid.uuid4(), cause="NEW_CAUSE")

        self.assertIsNone(result)
        session.commit.assert_not_awaited()

    async def test_update_service_alert_updates_and_returns_refreshed_alert(self):
        existing = SimpleNamespace(
            id=uuid.uuid4(),
            cause="OLD",
            effect="E",
            severity_level="S",
            is_active=True,
        )
        refreshed = SimpleNamespace(id=existing.id, cause="NEW")
        session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    _FakeResult(scalar_one_or_none_value=existing),
                    _FakeResult(scalar_one_or_none_value=refreshed),
                ]
            ),
            commit=AsyncMock(),
            add=lambda _: None,
        )
        repository = self._make_repository(session)

        result = await repository.update_service_alert(existing.id, cause="NEW")

        self.assertEqual(existing.cause, "NEW")
        self.assertEqual(result, refreshed)
        session.commit.assert_awaited_once()
        self.assertEqual(session.execute.await_count, 2)

    async def test_toggle_service_alert_active_returns_none_when_not_found(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(scalar_one_or_none_value=None)),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.toggle_service_alert_active(uuid.uuid4())

        self.assertIsNone(result)
        session.commit.assert_not_awaited()

    async def test_toggle_service_alert_active_toggles_and_returns_refreshed(self):
        alert = SimpleNamespace(id=uuid.uuid4(), is_active=True)
        refreshed = SimpleNamespace(id=alert.id, is_active=False)
        session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    _FakeResult(scalar_one_or_none_value=alert),
                    _FakeResult(scalar_one_or_none_value=refreshed),
                ]
            ),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.toggle_service_alert_active(alert.id)

        self.assertFalse(alert.is_active)
        self.assertEqual(result, refreshed)
        session.commit.assert_awaited_once()

    async def test_list_service_alerts_by_ids_returns_empty_for_no_ids(self):
        session = SimpleNamespace(execute=AsyncMock())
        repository = self._make_repository(session)

        result = await repository.list_service_alerts_by_ids([])

        self.assertEqual(result, [])
        session.execute.assert_not_awaited()

    async def test_list_service_alerts_by_ids_returns_alerts(self):
        alert = SimpleNamespace(id=uuid.uuid4())
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult([alert])))
        repository = self._make_repository(session)

        result = await repository.list_service_alerts_by_ids([alert.id])

        self.assertEqual(result, [alert])
        session.execute.assert_awaited_once()

    async def test_delete_service_alerts_for_data_source_by_ids_returns_zero_for_empty_ids(self):
        session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
        repository = self._make_repository(session)

        result = await repository.delete_service_alerts_for_data_source_by_ids(1, [])

        self.assertEqual(result, 0)
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_delete_service_alerts_for_data_source_by_ids_deletes_and_commits(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(rowcount=5)),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.delete_service_alerts_for_data_source_by_ids(1, [uuid.uuid4()])

        self.assertEqual(result, 5)
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_upsert_service_alert_from_sync_returns_created_for_new_alert(self):
        session = SimpleNamespace(
            get=AsyncMock(return_value=None),
            add=lambda _: None,
            flush=AsyncMock(),
            execute=AsyncMock(),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.upsert_service_alert_from_sync(
            alert_id=uuid.uuid4(),
            source_id=1,
            source_name="source",
            cause="UNKNOWN_CAUSE",
            effect="UNKNOWN_EFFECT",
            severity_level="UNKNOWN_SEVERITY",
            is_active_on_create=True,
            translations=[],
            active_periods=[],
            informed_entities=[],
        )

        self.assertEqual(result, "created")
        session.get.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_upsert_service_alert_from_sync_returns_updated_for_existing_alert(self):
        existing = SimpleNamespace(
            cause="OLD",
            effect="OLD",
            severity_level="OLD",
            source="old",
            data_source_id=10,
        )
        session = SimpleNamespace(
            get=AsyncMock(return_value=existing),
            add=lambda _: None,
            flush=AsyncMock(),
            execute=AsyncMock(),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.upsert_service_alert_from_sync(
            alert_id=uuid.uuid4(),
            source_id=2,
            source_name="new",
            cause="C",
            effect="E",
            severity_level="S",
            is_active_on_create=False,
            translations=[],
            active_periods=[],
            informed_entities=[],
        )

        self.assertEqual(result, "updated")
        self.assertEqual(existing.source, "new")
        self.assertEqual(existing.data_source_id, 2)
        session.commit.assert_awaited_once()

    async def test_get_realtime_trips_returns_loaded_trips(self):
        trip = SimpleNamespace(id="trip-1")
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult([trip])))
        repository = self._make_repository(session)

        items = await repository.get_realtime_trips()

        self.assertEqual(items, [trip])
        session.execute.assert_awaited_once()

    async def test_get_realtime_trips_returns_empty_list(self):
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult([])))
        repository = self._make_repository(session)

        items = await repository.get_realtime_trips()

        self.assertEqual(items, [])
        session.execute.assert_awaited_once()

    async def test_list_trips_paginated_returns_items_and_total(self):
        trip = SimpleNamespace(id="trip-1")
        session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    _FakeResult(scalar_one_value=12),
                    _FakeResult([trip]),
                ]
            )
        )
        repository = self._make_repository(session)

        items, total = await repository.list_trips_paginated(
            page=1,
            limit=20,
            sort="asc",
            search="",
            is_active=None,
        )

        self.assertEqual(items, [trip])
        self.assertEqual(total, 12)
        self.assertEqual(session.execute.await_count, 2)

    async def test_list_trip_ids_with_invalid_stop_events_returns_empty_for_no_trip_ids(self):
        session = SimpleNamespace(execute=AsyncMock())
        repository = self._make_repository(session)

        result = await repository.list_trip_ids_with_invalid_stop_events([])

        self.assertEqual(result, set())
        session.execute.assert_not_awaited()

    async def test_list_trip_ids_with_invalid_stop_events_returns_trip_ids(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(rows=[("trip-a",), ("trip-b",)]))
        )
        repository = self._make_repository(session)

        result = await repository.list_trip_ids_with_invalid_stop_events(["trip-a", "trip-b", "trip-c"])

        self.assertEqual(result, {"trip-a", "trip-b"})
        session.execute.assert_awaited_once()

    async def test_toggle_trip_active_returns_none_when_not_found(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(scalar_one_or_none_value=None)),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.toggle_trip_active(uuid.uuid4())

        self.assertIsNone(result)
        session.commit.assert_not_awaited()

    async def test_toggle_trip_active_toggles_and_returns_refreshed_trip(self):
        trip = SimpleNamespace(id=uuid.uuid4(), is_active=True)
        refreshed = SimpleNamespace(id=trip.id, is_active=False)
        session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    _FakeResult(scalar_one_or_none_value=trip),
                    _FakeResult(scalar_one_or_none_value=refreshed),
                ]
            ),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.toggle_trip_active(trip.id)

        self.assertFalse(trip.is_active)
        self.assertEqual(result, refreshed)
        session.commit.assert_awaited_once()

    async def test_delete_trips_for_data_source_returns_rowcount(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(rowcount=6)),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.delete_trips_for_data_source(3)

        self.assertEqual(result, 6)
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_get_realtime_vehicles_returns_loaded_vehicles(self):
        vehicle = SimpleNamespace(id="vehicle-1")
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult([vehicle])))
        repository = self._make_repository(session)

        items = await repository.get_realtime_vehicles()

        self.assertEqual(items, [vehicle])
        session.execute.assert_awaited_once()

    async def test_get_realtime_vehicles_returns_empty_list(self):
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult([])))
        repository = self._make_repository(session)

        items = await repository.get_realtime_vehicles()

        self.assertEqual(items, [])
        session.execute.assert_awaited_once()

    async def test_list_vehicles_paginated_returns_items_and_total(self):
        vehicle = SimpleNamespace(id="vehicle-1")
        session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    _FakeResult(scalar_one_value=4),
                    _FakeResult([vehicle]),
                ]
            )
        )
        repository = self._make_repository(session)

        items, total = await repository.list_vehicles_paginated(
            page=1,
            limit=50,
            search="",
            is_active=None,
        )

        self.assertEqual(items, [vehicle])
        self.assertEqual(total, 4)
        self.assertEqual(session.execute.await_count, 2)

    async def test_toggle_vehicle_active_returns_none_when_not_found(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(scalar_one_or_none_value=None)),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.toggle_vehicle_active(uuid.uuid4())

        self.assertIsNone(result)
        session.commit.assert_not_awaited()

    async def test_toggle_vehicle_active_toggles_and_returns_refreshed_vehicle(self):
        vehicle = SimpleNamespace(id=uuid.uuid4(), is_active=True)
        refreshed = SimpleNamespace(id=vehicle.id, is_active=False)
        session = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    _FakeResult(scalar_one_or_none_value=vehicle),
                    _FakeResult(scalar_one_or_none_value=refreshed),
                ]
            ),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.toggle_vehicle_active(vehicle.id)

        self.assertFalse(vehicle.is_active)
        self.assertEqual(result, refreshed)
        session.commit.assert_awaited_once()

    async def test_delete_vehicles_for_data_source_returns_rowcount(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=_FakeResult(rowcount=8)),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.delete_vehicles_for_data_source(5)

        self.assertEqual(result, 8)
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_update_trip_update_from_sync_returns_created_for_new_trip(self):
        added_objects = []
        session = SimpleNamespace(
            get=AsyncMock(return_value=None),
            add=lambda obj: added_objects.append(obj),
            flush=AsyncMock(),
            execute=AsyncMock(),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.update_trip_update_from_sync(
            trip_uuid=uuid.uuid4(),
            source_id=11,
            source_name="source-a",
            trip_id="trip-1",
            start_time="08:00:00",
            start_date="20260801",
            route_id="route-1",
            schedule_relationship="SCHEDULED",
            assignment_type="ASSIGNED",
            is_active_on_create=False,
            is_valid=True,
            stop_events=[
                {
                    "stop_id": "stop-1",
                    "stop_sequence": "1",
                    "arrival_time": "2026-08-01T08:00:00Z",
                    "departure_time": "2026-08-01T08:01:00Z",
                    "schedule_relationship": "SCHEDULED",
                    "is_valid": True,
                }
            ],
        )

        self.assertEqual(result, "created")
        session.get.assert_awaited_once()
        session.flush.assert_awaited_once()
        self.assertEqual(session.execute.await_count, 1)
        session.commit.assert_awaited_once()
        self.assertEqual(len(added_objects), 2)

    async def test_update_trip_update_from_sync_preserves_is_active_on_existing_trip(self):
        existing = SimpleNamespace(
            trip_id="old-trip",
            is_active=True,
            data_source_id=1,
            source="old",
            start_time="07:00:00",
            start_date="20260801",
            route_id="old-route",
            schedule_relationship="SCHEDULED",
            assignment_type="ASSIGNED",
            is_valid=False,
        )
        session = SimpleNamespace(
            get=AsyncMock(return_value=existing),
            add=lambda _: None,
            flush=AsyncMock(),
            execute=AsyncMock(),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.update_trip_update_from_sync(
            trip_uuid=uuid.uuid4(),
            source_id=22,
            source_name="source-b",
            trip_id="trip-2",
            start_time="09:00:00",
            start_date="20260802",
            route_id="route-2",
            schedule_relationship="ADDED",
            assignment_type="DUPLICATED",
            is_active_on_create=False,
            is_valid=True,
            stop_events=[],
        )

        self.assertEqual(result, "updated")
        self.assertTrue(existing.is_active)
        self.assertEqual(existing.trip_id, "trip-2")
        self.assertEqual(existing.data_source_id, 22)
        self.assertEqual(existing.source, "source-b")
        self.assertEqual(existing.is_valid, True)
        session.flush.assert_not_awaited()
        session.commit.assert_awaited_once()

    async def test_update_vehicle_position_from_sync_returns_created_for_new_vehicle(self):
        added_objects = []
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[None, None]),
            add=lambda obj: added_objects.append(obj),
            flush=AsyncMock(),
            execute=AsyncMock(),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.update_vehicle_position_from_sync(
            vehicle_uuid=uuid.uuid4(),
            source_id=33,
            source_name="source-c",
            trip_uuid=uuid.uuid4(),
            trip_id="trip-3",
            trip_start_time="10:00:00",
            trip_start_date="20260803",
            trip_route_id="route-3",
            trip_schedule_relationship="SCHEDULED",
            trip_assignment_type="ASSIGNED",
            trip_is_active_on_create=True,
            trip_is_valid=True,
            vehicle_id="veh-1",
            vehicle_label="Label 1",
            vehicle_license_plate="ABC123",
            vehicle_wheelchair_accessible="NO_VALUE",
            timestamp="2026-08-01T10:00:00Z",
            latitude=47.0,
            longitude=8.0,
            current_stop_sequence=3,
            current_status="IN_TRANSIT_TO",
            assignment_type="ASSIGNED",
            congestion_level="UNKNOWN_CONGESTION_LEVEL",
            is_active_on_create=False,
            is_valid=True,
        )

        self.assertEqual(result, "created")
        self.assertEqual(session.get.await_count, 2)
        self.assertEqual(session.flush.await_count, 2)
        self.assertEqual(len(added_objects), 2)
        session.commit.assert_awaited_once()

    async def test_update_vehicle_position_from_sync_preserves_is_active_on_existing_records(self):
        existing_trip = SimpleNamespace(
            is_active=True,
            data_source_id=1,
            source="old",
            trip_id="old-trip",
            start_time="07:00:00",
            start_date="20260801",
            route_id="old-route",
            schedule_relationship="SCHEDULED",
            assignment_type="ASSIGNED",
            is_valid=False,
        )
        existing_vehicle = SimpleNamespace(
            is_active=True,
            data_source_id=1,
            source="old",
            trip_id="old-trip",
            vehicle_id="old-veh",
            vehicle_label=None,
            vehicle_license_plate=None,
            vehicle_wheelchair_accessible="NO_VALUE",
            timestamp="2026-08-01T07:00:00Z",
            latitude=0.0,
            longitude=0.0,
            current_stop_sequence=0,
            current_status="IN_TRANSIT_TO",
            assignment_type="ASSIGNED",
            congestion_level="UNKNOWN_CONGESTION_LEVEL",
            is_valid=False,
        )
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[existing_trip, existing_vehicle]),
            add=lambda _: None,
            flush=AsyncMock(),
            execute=AsyncMock(),
            commit=AsyncMock(),
        )
        repository = self._make_repository(session)

        result = await repository.update_vehicle_position_from_sync(
            vehicle_uuid=uuid.uuid4(),
            source_id=44,
            source_name="source-d",
            trip_uuid=uuid.uuid4(),
            trip_id="trip-4",
            trip_start_time="11:00:00",
            trip_start_date="20260804",
            trip_route_id="route-4",
            trip_schedule_relationship="ADDED",
            trip_assignment_type="DUPLICATED",
            trip_is_active_on_create=False,
            trip_is_valid=True,
            vehicle_id="veh-2",
            vehicle_label="Label 2",
            vehicle_license_plate="XYZ987",
            vehicle_wheelchair_accessible="POSSIBLE",
            timestamp="2026-08-01T11:00:00Z",
            latitude=48.0,
            longitude=9.0,
            current_stop_sequence=5,
            current_status="STOPPED_AT",
            assignment_type="DUPLICATED",
            congestion_level="RUNNING_SMOOTHLY",
            is_active_on_create=False,
            is_valid=True,
        )

        self.assertEqual(result, "updated")
        self.assertTrue(existing_trip.is_active)
        self.assertTrue(existing_vehicle.is_active)
        self.assertEqual(existing_trip.trip_id, "trip-4")
        self.assertEqual(existing_vehicle.vehicle_id, "veh-2")
        self.assertEqual(existing_vehicle.trip_id, "trip-4")
        session.flush.assert_not_awaited()
        session.commit.assert_awaited_once()
