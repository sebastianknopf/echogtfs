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


class TestGtfsRealtimeTripUpdatesExportService(unittest.IsolatedAsyncioTestCase):
    async def test_export_protobuf_returns_serialized_feed(self):
        repo = SimpleNamespace(get_realtime_trips=AsyncMock(return_value=[]))
        service = GtfsRealtimeTripUpdatesExportService(repo)
        fake_feed = SimpleNamespace(SerializeToString=lambda: b"trip-bytes")

        with patch.object(service, "_build_feed_message", return_value=fake_feed) as build_feed:
            payload = await service.export_protobuf()

        self.assertEqual(payload, b"trip-bytes")
        build_feed.assert_called_once_with([])

    async def test_export_json_contains_trip_update_payload(self):
        trip = self._make_trip()
        repo = SimpleNamespace(get_realtime_trips=AsyncMock(return_value=[trip]))
        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = GtfsRealtimeTripUpdatesExportService(repo)

            with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
                payload = await service.export_json()

        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(data["header"]["gtfs_realtime_version"], "2.0")
        self.assertEqual(len(data["entity"]), 1)
        entity = data["entity"][0]
        self.assertEqual(entity["id"], "trip-row-id")
        self.assertEqual(entity["trip_update"]["trip"]["trip_id"], "TRIP-1")
        self.assertEqual(entity["trip_update"]["trip"]["schedule_relationship"], "SCHEDULED")
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
            service = GtfsRealtimeTripUpdatesExportService(SimpleNamespace())
        trip_without_events = self._make_trip(stop_events=[])

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([trip_without_events])

        self.assertEqual(len(feed.entity), 0)

    def test_build_feed_message_ignores_invalid_optional_values(self):
        invalid_vehicle = SimpleNamespace(
            id="vehicle-row-id",
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
            service = GtfsRealtimeTripUpdatesExportService(SimpleNamespace())

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([trip])

        entity = feed.entity[0]
        self.assertFalse(entity.trip_update.trip.HasField("schedule_relationship"))
        self.assertFalse(entity.trip_update.vehicle.HasField("wheelchair_accessible"))
        self.assertFalse(entity.trip_update.stop_time_update[0].HasField("stop_sequence"))
        self.assertFalse(entity.trip_update.stop_time_update[0].HasField("schedule_relationship"))

    def test_stop_sequence_value_returns_none_for_invalid_value(self):
        self.assertIsNone(
            GtfsRealtimeTripUpdatesExportService._stop_sequence_value(SimpleNamespace(stop_sequence="abc"))
        )

    def test_build_feed_message_converts_start_time_to_configured_timezone(self):
        trip = self._make_trip(start_time="08:00:00")
        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="Europe/Berlin",
        ):
            service = GtfsRealtimeTripUpdatesExportService(SimpleNamespace())

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_trip_updates_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([trip])

        self.assertEqual(feed.entity[0].trip_update.trip.start_time, "10:00:00")

    def test_build_feed_message_formats_next_day_departure_above_23_hours(self):
        trip = self._make_trip(start_time="23:30:00")
        with patch.object(
            GtfsRealtimeTripUpdatesExportService,
            "_configured_timezone_name",
            return_value="Europe/Berlin",
        ):
            service = GtfsRealtimeTripUpdatesExportService(SimpleNamespace())

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
            service = GtfsRealtimeTripUpdatesExportService(SimpleNamespace())

        self.assertEqual(service._localize_start_time(trip.start_date, trip.start_time), "08:00:00")

    @staticmethod
    def _make_trip(
        *,
        schedule_relationship: str = "SCHEDULED",
        start_time: str = "08:00:00",
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
                vehicle_label="Vehicle Label",
                vehicle_license_plate="ABC-123",
                vehicle_wheelchair_accessible="WHEELCHAIR_ACCESSIBLE",
            )

        return SimpleNamespace(
            id="trip-row-id",
            trip_id="TRIP-1",
            route_id="ROUTE-1",
            start_time=start_time,
            start_date="20260721",
            schedule_relationship=schedule_relationship,
            updated_at=1700000001,
            stop_events=stop_events,
            vehicle=vehicle,
        )
