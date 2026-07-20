from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.mapping.mapping_import_service import MappingImportService
from echogtfs.services.mapping.mapping_service_error import MappingServiceError


class TestMappingImportService(unittest.IsolatedAsyncioTestCase):
    async def test_import_csv_stream_success(self):
        repo = SimpleNamespace(
            get_data_source_by_id=AsyncMock(return_value=SimpleNamespace(id=1)),
            replace_data_source_mappings_for_entity_type=AsyncMock(),
        )

        importer = MappingImportService()
        imported = await importer.import_csv_stream(
            repository=repo,
            source_id=1,
            entity_type="route",
            stream=io.BytesIO(b"a;b\nc;d\n"),
            filename="mappings.csv",
        )

        self.assertEqual(imported, 2)

    async def test_import_rejects_invalid_extension(self):
        repo = SimpleNamespace(get_data_source_by_id=AsyncMock(return_value=SimpleNamespace(id=1)))
        importer = MappingImportService()

        with self.assertRaises(MappingServiceError):
            await importer.import_csv_stream(repo, 1, "route", io.BytesIO(b"a;b"), "x.txt")