from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

fake_config = types.ModuleType("echogtfs.common.config")
fake_config.settings = SimpleNamespace(secret_key="test-secret")
fake_config.Settings = object
sys.modules.setdefault("echogtfs.common.config", fake_config)

from fastapi import HTTPException

from echogtfs.routers import realtime


class TestRealtimeRouter(unittest.IsolatedAsyncioTestCase):
    async def test_get_realtime_feed_returns_service_alerts_json(self):
        repository = SimpleNamespace(get_all_app_settings=AsyncMock(return_value={
            "gtfs_rt_service_alerts_path": "realtime/service-alerts.pbf",
            "gtfs_rt_trip_updates_path": "realtime/trip-updates.pbf",
            "gtfs_rt_vehicle_positions_path": "realtime/vehicle-positions.pbf",
            "gtfs_rt_username": "",
            "gtfs_rt_password": "",
        }))
        export_service = SimpleNamespace(export_json=AsyncMock(return_value=b'{"kind":"alerts"}'))

        with patch("echogtfs.routers.realtime.get_system_repository", return_value=repository), patch(
            "echogtfs.routers.realtime.get_realtime_repository", return_value=SimpleNamespace()
        ), patch(
            "echogtfs.routers.realtime.GtfsRealtimeServiceAlertsExportService",
            return_value=export_service,
        ):
            response = await realtime.get_realtime_feed(
                "realtime/service-alerts.pbf",
                request=SimpleNamespace(),
                _auth=None,
                json_format="1",
                debug_format=None,
            )

        self.assertEqual(response.media_type, "application/json")
        self.assertEqual(response.body, b'{"kind":"alerts"}')
        export_service.export_json.assert_awaited_once()

    async def test_get_realtime_feed_returns_trip_updates_protobuf(self):
        repository = SimpleNamespace(get_all_app_settings=AsyncMock(return_value={
            "gtfs_rt_service_alerts_path": "realtime/service-alerts.pbf",
            "gtfs_rt_trip_updates_path": "realtime/trip-updates.pbf",
            "gtfs_rt_vehicle_positions_path": "realtime/vehicle-positions.pbf",
            "gtfs_rt_username": "",
            "gtfs_rt_password": "",
        }))
        export_service = SimpleNamespace(export_protobuf=AsyncMock(return_value=b"trip-bytes"))

        with patch("echogtfs.routers.realtime.get_system_repository", return_value=repository), patch(
            "echogtfs.routers.realtime.get_realtime_repository", return_value=SimpleNamespace()
        ), patch(
            "echogtfs.routers.realtime.GtfsRealtimeTripUpdatesExportService",
            return_value=export_service,
        ):
            response = await realtime.get_realtime_feed(
                "realtime/trip-updates.pbf",
                request=SimpleNamespace(),
                _auth=None,
                json_format=None,
                debug_format=None,
            )

        self.assertEqual(response.media_type, "application/x-protobuf")
        self.assertEqual(response.body, b"trip-bytes")
        export_service.export_protobuf.assert_awaited_once()

    async def test_get_realtime_feed_returns_vehicle_positions_json(self):
        repository = SimpleNamespace(get_all_app_settings=AsyncMock(return_value={
            "gtfs_rt_service_alerts_path": "realtime/service-alerts.pbf",
            "gtfs_rt_trip_updates_path": "realtime/trip-updates.pbf",
            "gtfs_rt_vehicle_positions_path": "realtime/vehicle-positions.pbf",
            "gtfs_rt_username": "",
            "gtfs_rt_password": "",
        }))
        export_service = SimpleNamespace(export_json=AsyncMock(return_value=b'{"kind":"vehicles"}'))

        with patch("echogtfs.routers.realtime.get_system_repository", return_value=repository), patch(
            "echogtfs.routers.realtime.get_realtime_repository", return_value=SimpleNamespace()
        ), patch(
            "echogtfs.routers.realtime.GtfsRealtimeVehiclePositionsExportService",
            return_value=export_service,
        ):
            response = await realtime.get_realtime_feed(
                "realtime/vehicle-positions.pbf",
                request=SimpleNamespace(),
                _auth=None,
                json_format=None,
                debug_format="1",
            )

        self.assertEqual(response.media_type, "application/json")
        self.assertEqual(response.body, b'{"kind":"vehicles"}')
        export_service.export_json.assert_awaited_once()

    async def test_get_realtime_feed_raises_404_for_unknown_path(self):
        repository = SimpleNamespace(get_all_app_settings=AsyncMock(return_value={
            "gtfs_rt_service_alerts_path": "realtime/service-alerts.pbf",
            "gtfs_rt_trip_updates_path": "realtime/trip-updates.pbf",
            "gtfs_rt_vehicle_positions_path": "realtime/vehicle-positions.pbf",
            "gtfs_rt_username": "",
            "gtfs_rt_password": "",
        }))

        with patch("echogtfs.routers.realtime.get_system_repository", return_value=repository), patch(
            "echogtfs.routers.realtime.get_realtime_repository", return_value=SimpleNamespace()
        ):
            with self.assertRaises(HTTPException) as context:
                await realtime.get_realtime_feed(
                    "realtime/unknown.pbf",
                    request=SimpleNamespace(),
                    _auth=None,
                    json_format=None,
                    debug_format=None,
                )

        self.assertEqual(context.exception.status_code, 404)
