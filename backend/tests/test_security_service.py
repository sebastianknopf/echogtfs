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
    global_id_pattern=None,
)
fake_config.Settings = object
sys.modules["echogtfs.common.config"] = fake_config

from echogtfs.enum.system import UserRole
from echogtfs.services.security.security_service import SecurityService


class TestSecurityService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        SecurityService._instance = None

    async def test_token_roundtrip_and_role_checks(self):
        user = SimpleNamespace(
            username="admin",
            is_active=True,
            role=UserRole.ADMIN,
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
            role=UserRole.USER,
        )
        repo = SimpleNamespace(get_user_by_username=AsyncMock(return_value=user))
        service = SecurityService(repo)
        token = service.create_access_token("u")

        with self.assertRaises(HTTPException):
            await service.get_current_active_user(SimpleNamespace(state=SimpleNamespace()), token)

    async def test_role_hierarchy(self):
        expectations = {
            UserRole.API: {"api": True, "regular": False, "poweruser": False, "superuser": False},
            UserRole.USER: {"api": True, "regular": True, "poweruser": False, "superuser": False},
            UserRole.POWERUSER: {"api": True, "regular": True, "poweruser": True, "superuser": False},
            UserRole.ADMIN: {"api": True, "regular": True, "poweruser": True, "superuser": True},
        }

        for role, expected in expectations.items():
            user = SimpleNamespace(username="u", is_active=True, role=role)
            service = SecurityService(SimpleNamespace(get_user_by_username=AsyncMock(return_value=user)))
            token = service.create_access_token("u")
            checks = {
                "api": service.get_current_api_user,
                "regular": service.get_current_regular_user,
                "poweruser": service.get_current_poweruser_or_admin,
                "superuser": service.get_current_superuser,
            }

            for name, check in checks.items():
                with self.subTest(role=role, check=name):
                    request = SimpleNamespace(state=SimpleNamespace())
                    if expected[name]:
                        await check(request, token)
                    else:
                        with self.assertRaises(HTTPException) as ctx:
                            await check(request, token)
                        self.assertEqual(ctx.exception.status_code, 403)

            SecurityService._instance = None

    async def test_invalid_token_rejected(self):
        repo = SimpleNamespace(get_user_by_username=AsyncMock(return_value=None))
        service = SecurityService(repo)

        with self.assertRaises(HTTPException):
            await service.get_current_user(
                SimpleNamespace(state=SimpleNamespace()),
                "not-a-jwt-token",
            )