from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.datalog.datalog_service import DatalogService
from echogtfs.services.datalog import datalog_service as datalog_module


class TestDatalogService(unittest.IsolatedAsyncioTestCase):
    async def test_create_log_entry_persists_file_and_calls_repository(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["DATASOURCE_LOG_DIR"] = tmp_dir
            repo = SimpleNamespace(
                create_data_source_log=AsyncMock(return_value=SimpleNamespace(id=123))
            )
            service = DatalogService(repo)

            entry = await service.create_log_entry(
                data_source_id=1,
                request_url="https://x",
                response_content="payload",
                request_headers={"a": "b"},
                response_headers={"c": "d"},
                response_mimetype="text/plain",
                status_code=200,
            )

            self.assertEqual(entry.id, 123)
            repo.create_data_source_log.assert_awaited_once()

    async def test_get_log_content_returns_none_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["DATASOURCE_LOG_DIR"] = tmp_dir
            service = DatalogService(SimpleNamespace())

            with patch.object(datalog_module.logger, "warning"):
                content = await service.get_log_content(uuid.uuid4())

            self.assertIsNone(content)