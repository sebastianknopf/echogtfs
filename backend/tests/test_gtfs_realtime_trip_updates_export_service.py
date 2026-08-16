from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service import (
    GtfsRealtimeTripUpdatesExportService,
)
from echogtfs import gtfs_realtime_pb2


class TestGtfsRealtimeTripUpdatesExportService(unittest.IsolatedAsyncioTestCase):
    async def test_export_protobuf_returns_serialized_feed(self):
        repo = SimpleNamespace(get_realtime_trips=AsyncMock(return_value=[]))
        system_repository = SimpleNamespace(get_app_setting=AsyncMock(return_value="false"))
        service = GtfsRealtimeTripUpdatesExportService(repo, system_repository)
        fake_feed = SimpleNamespace(SerializeToString=lambda: b"trip-bytes")

        with patch.object(service, "_build_feed_message", return_value=fake_feed) as build_feed:
            payload = await service.export_protobuf()

        self.assertEqual(payload, b"trip-bytes")
        build_feed.assert_called_once_with([])
        system_repository.get_app_setting.assert_awaited_once()

    async def test_export_json_contains_trip_update_payload(self):
        trip = self._make_trip()
        repo = SimpleNamespace(get_realtime_trips=AsyncMock(return_value=[trip]))
        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = GtfsRealtimeTripUpdatesExportService(
                repo,
                SimpleNamespace(get_app_setting=AsyncMock(return_value="false")),
            )

            with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
                payload = await service.export_json()

        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["header"]["gtfs_realtime_version"], "2.0")
        self.assertEqual(len(data["entity"]), 1)
        entity = data["entity"][0]
        self.assertEqual(entity["id"], "trip-row-id")
        self.assertEqual(entity["trip_update"]["trip"]["trip_id"], "TRIP-1")
        self.assertEqual(entity["trip_update"]["trip"]["schedule_relationship"], "SCHEDULED")
        self.assertEqual(entity["trip_update"]["vehicle"]["id"], "BUS-1")
        self.assertEqual(entity["trip_update"]["vehicle"]["wheelchair_accessible"], "WHEELCHAIR_ACCESSIBLE")
        self.assertEqual(
            entity["trip_update"]["stop_time_update"][0]["schedule_relationship"],
            "SCHEDULED",
        )

    def test_build_feed_message_skips_trips_without_stop_events(self):
        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = self._make_service()
        trip_without_events = self._make_trip(stop_events=[])

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([trip_without_events])

        self.assertEqual(len(feed.entity), 0)

    async def test_load_trips_excludes_trips_with_only_no_data_stop_events_when_enabled(self):
        no_data_trip = self._make_trip(
            stop_events=[
                SimpleNamespace(
                    stop_id="STOP-1",
                    stop_sequence="1",
                    schedule_relationship="NO_DATA",
                    arrival_time=1700000100,
                    departure_time=1700000200,
                )
            ]
        )
        scheduled_trip = self._make_trip()
        scheduled_trip.id = "scheduled-trip-row-id"
        scheduled_trip.trip_id = "TRIP-2"

        realtime_repository = SimpleNamespace(
            get_realtime_trips=AsyncMock(return_value=[no_data_trip, scheduled_trip])
        )
        system_repository = SimpleNamespace(get_app_setting=AsyncMock(return_value="true"))
        service = self._make_service(realtime_repository, system_repository)

        trips = await service._load_trips()

        self.assertEqual(trips, [scheduled_trip])
        system_repository.get_app_setting.assert_awaited_once()

    def test_build_feed_message_exports_deleted_and_canceled_trips_without_stop_events(self):
        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = self._make_service()

        scheduled_trip_without_events = self._make_trip(stop_events=[], schedule_relationship="SCHEDULED")
        canceled_trip_without_events = self._make_trip(stop_events=[], schedule_relationship="CANCELED")
        deleted_trip_without_events = self._make_trip(stop_events=[], schedule_relationship="DELETED")

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message(
                [
                    scheduled_trip_without_events,
                    canceled_trip_without_events,
                    deleted_trip_without_events,
                ]
            )

        self.assertEqual(len(feed.entity), 2)
        self.assertEqual(
            feed.entity[0].trip_update.trip.schedule_relationship,
            gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.CANCELED,
        )
        self.assertEqual(
            feed.entity[1].trip_update.trip.schedule_relationship,
            gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.DELETED,
        )
        self.assertEqual(len(feed.entity[0].trip_update.stop_time_update), 0)
        self.assertEqual(len(feed.entity[1].trip_update.stop_time_update), 0)

    def test_build_feed_message_ignores_invalid_optional_values(self):
        invalid_vehicle = SimpleNamespace(
            id="vehicle-row-id",
            vehicle_id="BUS-1",
            vehicle_label="Label",
            vehicle_license_plate="Plate",
            vehicle_wheelchair_accessible="NOT_VALID",
        )
        invalid_stop_event = SimpleNamespace(
            stop_id="STOP-1",
            stop_sequence="invalid",
            schedule_relationship="NOT_VALID",
            arrival_time=None,
            departure_time=None,
        )
        trip = self._make_trip(
            schedule_relationship="NOT_VALID",
            stop_events=[invalid_stop_event],
            vehicle=invalid_vehicle,
        )
        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = self._make_service()

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([trip])

        entity = feed.entity[0]
        self.assertFalse(entity.trip_update.trip.HasField("schedule_relationship"))
        self.assertFalse(entity.trip_update.vehicle.HasField("wheelchair_accessible"))
        self.assertEqual(entity.trip_update.stop_time_update[0].stop_sequence, 1)
        self.assertFalse(entity.trip_update.stop_time_update[0].HasField("schedule_relationship"))

    def test_stop_sequence_value_returns_none_for_invalid_value(self):
        self.assertIsNone(
            GtfsRealtimeTripUpdatesExportService._stop_sequence_value(SimpleNamespace(stop_sequence="abc"))
        )

    def test_build_feed_message_omits_time_for_no_data_stop_events(self):
        no_data_event = SimpleNamespace(
            stop_id="STOP-1",
            stop_sequence="1",
            schedule_relationship="NO_DATA",
            arrival_time=1700000100,
            departure_time=1700000200,
        )
        scheduled_event = SimpleNamespace(
            stop_id="STOP-2",
            stop_sequence="2",
            schedule_relationship="SCHEDULED",
            arrival_time=1700000300,
            departure_time=1700000400,
        )
        trip = self._make_trip(stop_events=[no_data_event, scheduled_event])

        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = self._make_service()

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([trip])

        stop_time_updates = feed.entity[0].trip_update.stop_time_update
        self.assertFalse(stop_time_updates[0].HasField("arrival"))
        self.assertFalse(stop_time_updates[0].HasField("departure"))
        self.assertEqual(
            stop_time_updates[0].schedule_relationship,
            gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.ScheduleRelationship.NO_DATA,
        )
        self.assertEqual(stop_time_updates[1].arrival.time, 1700000300)
        self.assertEqual(stop_time_updates[1].departure.time, 1700000400)

    def test_build_feed_message_suppresses_added_stop_events_and_reindexes_sequence(self):
        stop_events = [
            SimpleNamespace(
                stop_id="STOP-1",
                stop_sequence="10",
                schedule_relationship="SCHEDULED",
                arrival_time=1700000100,
                departure_time=1700000200,
            ),
            SimpleNamespace(
                stop_id="STOP-ADDED",
                stop_sequence="20",
                schedule_relationship="ADDED",
                arrival_time=1700000300,
                departure_time=1700000400,
            ),
            SimpleNamespace(
                stop_id="STOP-2",
                stop_sequence="30",
                schedule_relationship="SKIPPED",
                arrival_time=1700000500,
                departure_time=1700000600,
            ),
        ]
        trip = self._make_trip(stop_events=stop_events)

        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = self._make_service()

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([trip])

        stop_time_updates = feed.entity[0].trip_update.stop_time_update
        self.assertEqual([update.stop_id for update in stop_time_updates], ["STOP-1", "STOP-2"])
        self.assertEqual([update.stop_sequence for update in stop_time_updates], [1, 2])

    def test_build_feed_message_skips_trips_with_only_added_stop_events(self):
        trip = self._make_trip(
            stop_events=[
                SimpleNamespace(
                    stop_id="STOP-ADDED",
                    stop_sequence="1",
                    schedule_relationship="ADDED",
                    arrival_time=1700000100,
                    departure_time=1700000200,
                )
            ]
        )

        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = self._make_service()

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([trip])

        self.assertEqual(len(feed.entity), 0)

    def test_build_feed_message_keeps_added_stops_as_scheduled_for_new_and_replacement_trips(self):
        for trip_relationship in ("NEW", "REPLACEMENT"):
            with self.subTest(schedule_relationship=trip_relationship):
                stop_events = [
                    SimpleNamespace(
                        stop_id="STOP-1",
                        stop_sequence="10",
                        schedule_relationship="SCHEDULED",
                        arrival_time=1700000100,
                        departure_time=1700000200,
                    ),
                    SimpleNamespace(
                        stop_id="STOP-ADDED",
                        stop_sequence="20",
                        schedule_relationship="ADDED",
                        arrival_time=1700000300,
                        departure_time=1700000400,
                    ),
                ]
                trip = self._make_trip(
                    schedule_relationship=trip_relationship,
                    stop_events=stop_events,
                )

                with patch.object(
                    GtfsRealtimeTripUpdatesExportService,
                    "_configured_timezone_name",
                    return_value="UTC",
                ):
                    service = self._make_service()

                with patch(
                    "echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time",
                    return_value=1700000000,
                ):
                    feed = service._build_feed_message([trip])

                stop_time_updates = feed.entity[0].trip_update.stop_time_update
                self.assertEqual(
                    [update.stop_id for update in stop_time_updates],
                    ["STOP-1", "STOP-ADDED"],
                )
                self.assertEqual([update.stop_sequence for update in stop_time_updates], [1, 2])
                self.assertEqual(
                    stop_time_updates[1].schedule_relationship,
                    gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.ScheduleRelationship.SCHEDULED,
                )
                self.assertEqual(stop_time_updates[1].arrival.time, 1700000300)
                self.assertEqual(stop_time_updates[1].departure.time, 1700000400)

    def test_stop_time_schedule_relationship_exposes_only_supported_values(self):
        enum_type = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.ScheduleRelationship
        exposed = {
            "SCHEDULED": enum_type.SCHEDULED,
            "SKIPPED": enum_type.SKIPPED,
            "NO_DATA": enum_type.NO_DATA,
            "scheduled": enum_type.SCHEDULED,
            " SKIPPED ": enum_type.SKIPPED,
        }

        for value, expected_enum in exposed.items():
            with self.subTest(schedule_relationship=value):
                self.assertEqual(
                    GtfsRealtimeTripUpdatesExportService._stop_time_schedule_relationship_to_enum(value),
                    expected_enum,
                )

        for value in ("ADDED", "UNSCHEDULED", "NOT_VALID", None):
            with self.subTest(schedule_relationship=value):
                self.assertIsNone(
                    GtfsRealtimeTripUpdatesExportService._stop_time_schedule_relationship_to_enum(value)
                )

        self.assertEqual(
            GtfsRealtimeTripUpdatesExportService._stop_time_schedule_relationship_to_enum(
                "ADDED",
                allow_added_stops=True,
            ),
            enum_type.SCHEDULED,
        )
        self.assertIsNone(
            GtfsRealtimeTripUpdatesExportService._stop_time_schedule_relationship_to_enum(
                "UNSCHEDULED",
                allow_added_stops=True,
            )
        )

    def test_build_feed_message_keeps_no_data_times_for_new_and_replacement_trips(self):
        for trip_relationship in ("NEW", "REPLACEMENT"):
            with self.subTest(schedule_relationship=trip_relationship):
                no_data_event = SimpleNamespace(
                    stop_id="STOP-1",
                    stop_sequence="1",
                    schedule_relationship="NO_DATA",
                    arrival_time=1700000100,
                    departure_time=1700000200,
                )
                trip = self._make_trip(
                    schedule_relationship=trip_relationship,
                    stop_events=[no_data_event],
                )

                with patch.object(
                    GtfsRealtimeTripUpdatesExportService,
                    "_configured_timezone_name",
                    return_value="UTC",
                ):
                    service = self._make_service()

                with patch(
                    "echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time",
                    return_value=1700000000,
                ):
                    feed = service._build_feed_message([trip])

                stop_time_update = feed.entity[0].trip_update.stop_time_update[0]
                self.assertTrue(stop_time_update.HasField("arrival"))
                self.assertTrue(stop_time_update.HasField("departure"))
                self.assertEqual(stop_time_update.arrival.time, 1700000100)
                self.assertEqual(stop_time_update.departure.time, 1700000200)

    def test_build_feed_message_converts_start_time_to_configured_timezone(self):
        trip = self._make_trip(start_time="08:00:00")
        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="Europe/Berlin",
        ):
            service = self._make_service()

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([trip])

        self.assertEqual(feed.entity[0].trip_update.trip.start_time, "10:00:00")

    def test_build_feed_message_normalizes_trip_start_date_to_yyyymmdd(self):
        trip = self._make_trip(start_date="2026-07-21")
        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = self._make_service()

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([trip])

        self.assertEqual(feed.entity[0].trip_update.trip.start_date, "20260721")

    def test_build_feed_message_formats_next_day_departure_above_23_hours(self):
        trip = self._make_trip(start_time="23:30:00")
        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="Europe/Berlin",
        ):
            service = self._make_service()

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([trip])

        self.assertEqual(feed.entity[0].trip_update.trip.start_time, "25:30:00")

    def test_localize_start_time_falls_back_to_original_for_invalid_timezone(self):
        trip = self._make_trip(start_time="08:00:00")
        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="Invalid/Timezone",
        ):
            service = self._make_service()

        self.assertEqual(service._localize_start_time(trip.start_date, trip.start_time), "08:00:00")

    @staticmethod
    def _make_service(
        realtime_repository: SimpleNamespace | None = None,
        system_repository: SimpleNamespace | None = None,
    ) -> GtfsRealtimeTripUpdatesExportService:
        return GtfsRealtimeTripUpdatesExportService(
            realtime_repository or SimpleNamespace(),
            system_repository or SimpleNamespace(get_app_setting=AsyncMock(return_value="false")),
        )

    @staticmethod
    def _make_trip(
        *,
        schedule_relationship: str = "SCHEDULED",
        start_time: str = "08:00:00",
        start_date: str = "20260721",
        stop_events: list[SimpleNamespace] | None = None,
        vehicle: SimpleNamespace | None = None,
    ) -> SimpleNamespace:
        if stop_events is None:
            stop_events = [
                SimpleNamespace(
                    stop_id="STOP-1",
                    stop_sequence="5",
                    schedule_relationship="SCHEDULED",
                    arrival_time=1700000100,
                    departure_time=1700000200,
                )
            ]

        if vehicle is None:
            vehicle = SimpleNamespace(
                id="vehicle-row-id",
                vehicle_id="BUS-1",
                vehicle_label="Vehicle Label",
                vehicle_license_plate="ABC-123",
                vehicle_wheelchair_accessible="WHEELCHAIR_ACCESSIBLE",
            )

        return SimpleNamespace(
            id="trip-row-id",
            trip_id="TRIP-1",
            route_id="ROUTE-1",
            start_time=start_time,
            start_date=start_date,
            schedule_relationship=schedule_relationship,
            updated_at=1700000001,
            stop_events=stop_events,
            vehicle=vehicle,
        )
