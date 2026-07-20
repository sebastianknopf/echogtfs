from __future__ import annotations

import io
import sys
import unittest
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.gtfs.gtfs_import_service import GtfsImportService, _TripWindow


class TestGtfsImportService(unittest.IsolatedAsyncioTestCase):
    async def test_run_import_task_success_sets_status(self):
        repo = SimpleNamespace(set_app_setting=AsyncMock())
        gtfs_repo = SimpleNamespace(replace_gtfs_static_data=AsyncMock())
        service = GtfsImportService(repo, gtfs_repo)

        with patch.object(service, "_import_feed", AsyncMock(return_value={"agencies": 1, "stops": 2, "routes": 3})):
            await service.run_import_task()

        self.assertTrue(repo.set_app_setting.await_count >= 5)

    def test_parse_map_helpers(self):
        csv_data = b"stop_id,stop_name,location_type\nS1,Main,0\nS2,,0\n"
        parsed = GtfsImportService._parse_csv(csv_data)
        stops = GtfsImportService._map_stops(parsed)
        self.assertEqual(stops, [{"gtfs_id": "S1", "name": "Main"}])

    def test_find_in_zip(self):
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w") as zf:
            zf.writestr("folder/agency.txt", "agency_id,agency_name\nA,Agency\n")
        mem.seek(0)

        with zipfile.ZipFile(mem) as zf:
            payload = GtfsImportService._find_in_zip(zf, "agency.txt")

        self.assertIn(b"agency_name", payload)

    async def test_import_feed_raises_when_feed_url_missing(self):
        repo = SimpleNamespace(get_all_app_settings=AsyncMock(return_value={}))
        gtfs_repo = SimpleNamespace(replace_gtfs_static_data=AsyncMock())
        service = GtfsImportService(repo, gtfs_repo)

        with self.assertRaises(ValueError):
            await service._import_feed()

    def test_find_in_zip_raises_when_missing_file(self):
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w") as zf:
            zf.writestr("folder/routes.txt", "route_id\nR1\n")
        mem.seek(0)

        with zipfile.ZipFile(mem) as zf:
            with self.assertRaises(KeyError):
                GtfsImportService._find_in_zip(zf, "agency.txt")

    def test_map_stop_time_row_updates_trip_window_and_uses_time_fallback(self):
        trip_windows: dict[str, object] = {}
        row = {
            "trip_id": "T1",
            "stop_id": "S1",
            "stop_sequence": "1",
            "arrival_time": "",
            "departure_time": "08:01:00",
        }

        mapped = GtfsImportService._map_stop_time_row(
            row,
            trip_meta={"T1": ("R1", 0)},
            stop_ids={"S1"},
            trip_windows=trip_windows,
        )

        self.assertIsNotNone(mapped)
        assert mapped is not None
        self.assertEqual(mapped["trip_id"], "T1")
        self.assertEqual(mapped["stop_id"], "S1")
        self.assertEqual(mapped["stop_sequence"], 1)
        self.assertEqual(mapped["arrival_time"], mapped["departure_time"])
        self.assertEqual(len(trip_windows), 1)

    def test_derive_trip_rows_uses_first_departure_and_last_arrival(self):
        start_departure = datetime(1970, 1, 1, 8, 5, 0, tzinfo=UTC)
        start_arrival = datetime(1970, 1, 1, 8, 4, 0, tzinfo=UTC)
        end_arrival = datetime(1970, 1, 1, 9, 0, 0, tzinfo=UTC)
        end_departure = datetime(1970, 1, 1, 9, 2, 0, tzinfo=UTC)

        trip_windows = {
            "T1": _TripWindow(
                first_sequence=1,
                first_stop_id="S1",
                first_arrival_time=start_arrival,
                first_departure_time=start_departure,
                last_sequence=5,
                last_stop_id="S5",
                last_arrival_time=end_arrival,
                last_departure_time=end_departure,
            )
        }

        trips = GtfsImportService._derive_trip_rows({"T1": ("R1", 1)}, trip_windows)

        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0]["gtfs_id"], "T1")
        self.assertEqual(trips[0]["route_id"], "R1")
        self.assertEqual(trips[0]["direction_id"], 1)
        self.assertEqual(trips[0]["start_stop_id"], "S1")
        self.assertEqual(trips[0]["end_stop_id"], "S5")
        self.assertEqual(trips[0]["start_time"], start_departure)
        self.assertEqual(trips[0]["end_time"], end_arrival)

    def test_parse_gtfs_time_supports_values_beyond_24_hours(self):
        value = GtfsImportService._parse_gtfs_time("25:10:05")

        self.assertIsNotNone(value)
        assert value is not None
        self.assertEqual(value, datetime(1970, 1, 2, 1, 10, 5, tzinfo=UTC))