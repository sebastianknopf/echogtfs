from __future__ import annotations

import io
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

fake_config = types.ModuleType("echogtfs.common.config")
fake_config.settings = SimpleNamespace(secret_key="test-secret", global_id_pattern=None)
fake_config.Settings = object
sys.modules.setdefault("echogtfs.common.config", fake_config)

from fastapi import HTTPException, UploadFile

from echogtfs.routers import systemcopy
from echogtfs.validation.schemas import SystemCopyExportSelection


class TestSystemCopyRouter(unittest.IsolatedAsyncioTestCase):
    async def test_export_system_copy_returns_zip_stream(self):
        service = SimpleNamespace(export_zip=AsyncMock(return_value=b"zip-bytes"))
        payload = SystemCopyExportSelection(system_settings=True)

        response = await systemcopy.export_system_copy(
            payload,
            _=None,
            service=service,
        )

        self.assertEqual(response.media_type, "application/zip")
        self.assertIn("attachment; filename=system-copy-", response.headers.get("Content-Disposition", ""))
        service.export_zip.assert_awaited_once()

    async def test_export_system_copy_maps_value_error_to_422(self):
        service = SimpleNamespace(export_zip=AsyncMock(side_effect=ValueError("invalid selection")))
        payload = SystemCopyExportSelection()

        with self.assertRaises(HTTPException) as ctx:
            await systemcopy.export_system_copy(
                payload,
                _=None,
                service=service,
            )

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail, "invalid selection")

    async def test_import_system_copy_rejects_non_zip(self):
        file = UploadFile(filename="copy.json", file=io.BytesIO(b"{}"))
        service = SimpleNamespace(import_zip=AsyncMock())

        with self.assertRaises(HTTPException) as ctx:
            await systemcopy.import_system_copy(
                _=None,
                service=service,
                file=file,
            )

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("Only .zip files are supported", str(ctx.exception.detail))
