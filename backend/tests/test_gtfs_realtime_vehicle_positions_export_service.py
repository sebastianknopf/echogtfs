from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.gtfsrt.gtfs_realtime_vehicle_positions_export_service import (
    GtfsRealtimeVehiclePositionsExportService,
)


class TestGtfsRealtimeVehiclePositionsExportService(unittest.IsolatedAsyncioTestCase):
    async def test_export_protobuf_returns_serialized_feed(self):
        repo = SimpleNamespace(get_realtime_vehicles=AsyncMock(return_value=[]))
        service = GtfsRealtimeVehiclePositionsExportService(repo)
        fake_feed = SimpleNamespace(SerializeToString=lambda: b"vehicle-bytes")

        with patch.object(service, "_build_feed_message", return_value=fake_feed) as build_feed:
            payload = await service.export_protobuf()

        self.assertEqual(payload, b"vehicle-bytes")
        build_feed.assert_called_once_with([])

    async def test_export_json_contains_vehicle_position_payload(self):
        vehicle = self._make_vehicle()
        repo = SimpleNamespace(get_realtime_vehicles=AsyncMock(return_value=[vehicle]))
        with patch.object(
            GtfsRealtimeVehiclePositionsExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = GtfsRealtimeVehiclePositionsExportService(repo)

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_vehicle_positions_export_service.time.time", return_value=1700000000):
            payload = await service.export_json()

        data = json.loads(payload.decode("utf-8"))
        self.assertEqual(len(data["entity"]), 1)
        entity = data["entity"][0]
        self.assertEqual(entity["id"], "vehicle-row-id")
        self.assertEqual(entity["vehicle"]["trip"]["trip_id"], "TRIP-1")
        self.assertEqual(entity["vehicle"]["trip"]["schedule_relationship"], "SCHEDULED")
        self.assertEqual(entity["vehicle"]["vehicle"]["id"], "BUS-1")
        self.assertEqual(entity["vehicle"]["position"]["latitude"], 47.0)
        self.assertEqual(entity["vehicle"]["current_status"], "STOPPED_AT")
        self.assertEqual(entity["vehicle"]["congestion_level"], "CONGESTION")

    def test_build_feed_message_maps_position_and_trip_descriptor(self):
        with patch.object(
            GtfsRealtimeVehiclePositionsExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = GtfsRealtimeVehiclePositionsExportService(SimpleNamespace())
        vehicle = self._make_vehicle()

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_vehicle_positions_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([vehicle])

        entity = feed.entity[0]
        self.assertEqual(entity.vehicle.position.latitude, 47.0)
        self.assertEqual(entity.vehicle.position.longitude, 8.0)
        self.assertEqual(entity.vehicle.current_stop_sequence, 7)
        self.assertEqual(entity.vehicle.trip.route_id, "ROUTE-1")
        self.assertEqual(entity.vehicle.vehicle.id, "BUS-1")

    def test_build_feed_message_ignores_invalid_optional_values(self):
        vehicle = self._make_vehicle(
            current_status="INVALID",
            congestion_level="INVALID",
            vehicle_wheelchair_accessible="INVALID",
            schedule_relationship="INVALID",
        )
        with patch.object(
            GtfsRealtimeVehiclePositionsExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = GtfsRealtimeVehiclePositionsExportService(SimpleNamespace())

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_vehicle_positions_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([vehicle])

        vehicle_position = feed.entity[0].vehicle
        self.assertFalse(vehicle_position.trip.HasField("schedule_relationship"))
        self.assertFalse(vehicle_position.vehicle.HasField("wheelchair_accessible"))
        self.assertFalse(vehicle_position.HasField("current_status"))
        self.assertFalse(vehicle_position.HasField("congestion_level"))

    def test_vehicle_id_value_falls_back_to_row_id(self):
        vehicle = self._make_vehicle(vehicle_id="")
        self.assertEqual(
            GtfsRealtimeVehiclePositionsExportService._vehicle_id_value(vehicle),
            "vehicle-row-id",
        )

    def test_build_feed_message_converts_start_time_to_configured_timezone(self):
        vehicle = self._make_vehicle(start_time="08:00:00")
        with patch.object(
            GtfsRealtimeVehiclePositionsExportService,
            "_configured_timezone_name",
            return_value="Europe/Berlin",
        ):
            service = GtfsRealtimeVehiclePositionsExportService(SimpleNamespace())

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_vehicle_positions_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([vehicle])

        self.assertEqual(feed.entity[0].vehicle.trip.start_time, "10:00:00")

    def test_build_feed_message_normalizes_trip_start_date_to_yyyymmdd(self):
        vehicle = self._make_vehicle(start_date="2026-07-21")
        with patch.object(
            GtfsRealtimeVehiclePositionsExportService,
            "_configured_timezone_name",
            return_value="UTC",
        ):
            service = GtfsRealtimeVehiclePositionsExportService(SimpleNamespace())

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_vehicle_positions_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([vehicle])

        self.assertEqual(feed.entity[0].vehicle.trip.start_date, "20260721")

    def test_build_feed_message_formats_next_day_departure_above_23_hours(self):
        vehicle = self._make_vehicle(start_time="23:30:00")
        with patch.object(
            GtfsRealtimeVehiclePositionsExportService,
            "_configured_timezone_name",
            return_value="Europe/Berlin",
        ):
            service = GtfsRealtimeVehiclePositionsExportService(SimpleNamespace())

        with patch("echogtfs.services.gtfsrt.gtfs_realtime_vehicle_positions_export_service.time.time", return_value=1700000000):
            feed = service._build_feed_message([vehicle])

        self.assertEqual(feed.entity[0].vehicle.trip.start_time, "25:30:00")

    def test_localize_start_time_falls_back_to_original_for_invalid_timezone(self):
        vehicle = self._make_vehicle(start_time="08:00:00")
        with patch.object(
            GtfsRealtimeVehiclePositionsExportService,
            "_configured_timezone_name",
            return_value="Invalid/Timezone",
        ):
            service = GtfsRealtimeVehiclePositionsExportService(SimpleNamespace())

        self.assertEqual(
            service._localize_start_time(vehicle.trip.start_date, vehicle.trip.start_time),
            "08:00:00",
        )

    @staticmethod
    def _make_vehicle(
        *,
        current_status: str = "STOPPED_AT",
        congestion_level: str = "CONGESTION",
        vehicle_wheelchair_accessible: str = "WHEELCHAIR_ACCESSIBLE",
        schedule_relationship: str = "SCHEDULED",
        vehicle_id: str = "BUS-1",
        start_time: str = "08:00:00",
        start_date: str = "20260721",
    ) -> SimpleNamespace:
        trip = SimpleNamespace(
            trip_id="TRIP-1",
            route_id="ROUTE-1",
            start_time=start_time,
            start_date=start_date,
            schedule_relationship=schedule_relationship,
        )
        return SimpleNamespace(
            id="vehicle-row-id",
            trip=trip,
            timestamp=1700000001,
            current_stop_sequence=7,
            vehicle_id=vehicle_id,
            vehicle_label="Vehicle Label",
            vehicle_license_plate="ABC-123",
            vehicle_wheelchair_accessible=vehicle_wheelchair_accessible,
            latitude=47.0,
            longitude=8.0,
            current_status=current_status,
            congestion_level=congestion_level,
        )
