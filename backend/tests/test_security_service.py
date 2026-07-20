from __future__ import annotations

import sys
import types
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi import HTTPException

fake_config = types.ModuleType("echogtfs.common.config")
fake_config.settings = SimpleNamespace(
    secret_key="test-secret-key-that-is-at-least-32-bytes-long",
    algorithm="HS256",
    access_token_expire_minutes=30,
)
fake_config.Settings = object
sys.modules["echogtfs.common.config"] = fake_config

from echogtfs.services.security.security_service import SecurityService


class TestSecurityService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        SecurityService._instance = None

    async def test_token_roundtrip_and_role_checks(self):
        user = SimpleNamespace(
            username="admin",
            is_active=True,
            is_superuser=True,
            is_technical_contact=False,
        )
        repo = SimpleNamespace(get_user_by_username=AsyncMock(return_value=user))
        service = SecurityService(repo)

        token = service.create_access_token("admin", expires_delta=timedelta(minutes=5))
        request = SimpleNamespace(state=SimpleNamespace())

        resolved_user = await service.get_current_superuser(request, token)

        self.assertEqual(resolved_user.username, "admin")
        self.assertEqual(request.state.user.username, "admin")

    async def test_inactive_user_rejected(self):
        user = SimpleNamespace(
            username="u",
            is_active=False,
            is_superuser=False,
            is_technical_contact=False,
        )
        repo = SimpleNamespace(get_user_by_username=AsyncMock(return_value=user))
        service = SecurityService(repo)
        token = service.create_access_token("u")

        with self.assertRaises(HTTPException):
            await service.get_current_active_user(SimpleNamespace(state=SimpleNamespace()), token)

    async def test_invalid_token_rejected(self):
        repo = SimpleNamespace(get_user_by_username=AsyncMock(return_value=None))
        service = SecurityService(repo)

        with self.assertRaises(HTTPException):
            await service.get_current_user(
                SimpleNamespace(state=SimpleNamespace()),
                "not-a-jwt-token",
            )