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


class TestCheckPushApiAuth(unittest.IsolatedAsyncioTestCase):
    async def test_raises_403_when_push_api_disabled(self):
        repository = _settings_repository({"push_api_enabled": "false"})

        with patch("echogtfs.routers.push.get_system_repository", return_value=repository):
            with self.assertRaises(HTTPException) as ctx:
                await push.check_push_api_auth(SimpleNamespace(headers={}))

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "error.push_api_disabled")

    async def test_allows_access_when_enabled_without_credentials_configured(self):
        repository = _settings_repository({
            "push_api_enabled": "true",
            "push_api_username": "",
            "push_api_password": "",
        })

        with patch("echogtfs.routers.push.get_system_repository", return_value=repository):
            await push.check_push_api_auth(SimpleNamespace(headers={}))

    async def test_raises_401_when_credentials_configured_but_missing_header(self):
        repository = _settings_repository({
            "push_api_enabled": "true",
            "push_api_username": "user",
            "push_api_password": "hashed",
        })

        with patch("echogtfs.routers.push.get_system_repository", return_value=repository):
            with self.assertRaises(HTTPException) as ctx:
                await push.check_push_api_auth(SimpleNamespace(headers={}))

        self.assertEqual(ctx.exception.status_code, 401)

    async def test_raises_422_on_wrong_username(self):
        repository = _settings_repository({
            "push_api_enabled": "true",
            "push_api_username": "user",
            "push_api_password": "hashed",
        })
        request = SimpleNamespace(headers={"Authorization": "Basic d3Jvbmc6cGFzcw=="})  # wrong:pass

        with patch("echogtfs.routers.push.get_system_repository", return_value=repository):
            with self.assertRaises(HTTPException) as ctx:
                await push.check_push_api_auth(request)

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail, "error.invalid_credentials")

    async def test_raises_422_on_wrong_password(self):
        repository = _settings_repository({
            "push_api_enabled": "true",
            "push_api_username": "user",
            "push_api_password": "hashed",
        })
        request = SimpleNamespace(headers={"Authorization": "Basic dXNlcjp3cm9uZw=="})  # user:wrong
        security_service = SimpleNamespace(verify_password=lambda password, hashed: False)

        with patch("echogtfs.routers.push.get_system_repository", return_value=repository), patch(
            "echogtfs.routers.push.get_security_service", return_value=security_service
        ):
            with self.assertRaises(HTTPException) as ctx:
                await push.check_push_api_auth(request)

        self.assertEqual(ctx.exception.status_code, 422)

    async def test_allows_access_with_correct_credentials(self):
        repository = _settings_repository({
            "push_api_enabled": "true",
            "push_api_username": "user",
            "push_api_password": "hashed",
        })
        request = SimpleNamespace(headers={"Authorization": "Basic dXNlcjpwYXNz"})  # user:pass
        security_service = SimpleNamespace(verify_password=lambda password, hashed: True)

        with patch("echogtfs.routers.push.get_system_repository", return_value=repository), patch(
            "echogtfs.routers.push.get_security_service", return_value=security_service
        ):
            await push.check_push_api_auth(request)


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
            response = await push.push_datasource(source_id=5, request=request, _=None)

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
                await push.push_datasource(source_id=5, request=request, _=None)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "error.source_not_active")


if __name__ == "__main__":
    unittest.main()
