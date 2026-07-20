from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.gtfs.gtfs_import_service import GtfsImportService


class TestGtfsImportService(unittest.IsolatedAsyncioTestCase):
    async def test_run_import_task_success_sets_status(self):
        repo = SimpleNamespace(set_app_setting=AsyncMock())
        service = GtfsImportService(repo)

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
        service = GtfsImportService(repo)

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