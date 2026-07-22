from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

fake_config = types.ModuleType("echogtfs.common.config")
fake_config.settings = SimpleNamespace(
    database_url="sqlite+aiosqlite://",
    secret_key="test-secret-key-that-is-at-least-32-bytes-long",
    algorithm="HS256",
    access_token_expire_minutes=30,
)
fake_config.Settings = object
sys.modules.setdefault("echogtfs.common.config", fake_config)

from echogtfs.services.database.alembic_migration_service import AlembicMigrationService


class TestAlembicMigrationService(unittest.IsolatedAsyncioTestCase):
    async def test_upgrade_head_uses_thread_offload(self):
        service = AlembicMigrationService()

        with patch("echogtfs.services.database.alembic_migration_service.asyncio.to_thread", new=AsyncMock()) as to_thread:
            await service.upgrade_head()

        to_thread.assert_awaited_once()

    def test_build_config_sets_required_values(self):
        service = AlembicMigrationService()
        config = service._build_config()

        self.assertTrue(config.get_main_option("script_location"))
        self.assertTrue(config.get_main_option("sqlalchemy.url"))