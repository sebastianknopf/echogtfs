from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

fake_config = types.ModuleType("echogtfs.common.config")
fake_config.settings = SimpleNamespace(secret_key="test-secret", global_id_pattern=None)
fake_config.Settings = object
sys.modules.setdefault("echogtfs.common.config", fake_config)

from fastapi import HTTPException

from echogtfs.routers import push
from echogtfs.services.scheduler.push_service_error import PushServiceError
from echogtfs.validation.schemas import PushResultResponse


def _settings_repository(rows: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(get_all_app_settings=AsyncMock(return_value=rows))


class TestCheckPushApiEnabled(unittest.IsolatedAsyncioTestCase):
    async def test_raises_403_when_push_api_disabled(self):
        repository = _settings_repository({"push_api_enabled": "false"})

        with patch("echogtfs.routers.push.get_system_repository", return_value=repository):
            with self.assertRaises(HTTPException) as ctx:
                await push.check_push_api_enabled()

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "error.push_api_disabled")

    async def test_allows_access_when_enabled(self):
        repository = _settings_repository({"push_api_enabled": "true"})

        with patch("echogtfs.routers.push.get_system_repository", return_value=repository):
            await push.check_push_api_enabled()


class TestPushDatasourceEndpoint(unittest.IsolatedAsyncioTestCase):
    async def test_returns_stats_on_success(self):
        scheduler = SimpleNamespace(
            run_push_task=AsyncMock(return_value={"added": 1, "updated": 2, "deleted": 0})
        )
        request = SimpleNamespace(
            body=AsyncMock(return_value=b"payload-bytes"),
            headers={"content-type": "application/xml"},
        )

        with patch("echogtfs.routers.push.get_datasource_scheduler_service", return_value=scheduler):
            response = await push.push_datasource(source_id=5, request=request, _user=None, _=None)

        self.assertIsInstance(response, PushResultResponse)
        self.assertEqual(response, PushResultResponse(added=1, updated=2, deleted=0))
        scheduler.run_push_task.assert_awaited_once_with(5, b"payload-bytes", "application/xml")

    async def test_maps_push_service_error_to_http_exception(self):
        scheduler = SimpleNamespace(
            run_push_task=AsyncMock(side_effect=PushServiceError(status_code=403, detail="error.source_not_active"))
        )
        request = SimpleNamespace(
            body=AsyncMock(return_value=b""),
            headers={"content-type": None},
        )

        with patch("echogtfs.routers.push.get_datasource_scheduler_service", return_value=scheduler):
            with self.assertRaises(HTTPException) as ctx:
                await push.push_datasource(source_id=5, request=request, _user=None, _=None)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "error.source_not_active")


if __name__ == "__main__":
    unittest.main()
