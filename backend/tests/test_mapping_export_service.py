from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.mapping.mapping_export_service import MappingExportService
from echogtfs.services.mapping.mapping_service_error import MappingServiceError


class TestMappingExportService(unittest.IsolatedAsyncioTestCase):
    async def test_export_csv_stream(self):
        repo = SimpleNamespace(
            get_data_source_by_id=AsyncMock(return_value=SimpleNamespace(id=1)),
            list_data_source_mappings=AsyncMock(
                return_value=[SimpleNamespace(key="a", value="b"), SimpleNamespace(key="c", value="d")]
            ),
        )

        exporter = MappingExportService()
        stream = await exporter.export_csv_stream(repo, 1, "route")
        rows = b"".join(stream)

        self.assertIn(b"a;b", rows)
        self.assertIn(b"c;d", rows)

    async def test_export_csv_stream_raises_when_source_missing(self):
        repo = SimpleNamespace(
            get_data_source_by_id=AsyncMock(return_value=None),
            list_data_source_mappings=AsyncMock(return_value=[]),
        )
        exporter = MappingExportService()

        with self.assertRaises(MappingServiceError):
            await exporter.export_csv_stream(repo, 999, "route")