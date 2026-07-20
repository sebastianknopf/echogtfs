from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.database.gtfs_repository import GtfsRepository


class TestGtfsRepository(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        GtfsRepository._instance = None

    async def test_repository_initializes_and_closes_engine(self):
        fake_engine = SimpleNamespace(dispose=AsyncMock())

        class _FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def execute(self, _stmt):
                return None

        class _Factory:
            def __call__(self):
                return _FakeSession()

        with patch("echogtfs.services.database.base.create_async_engine", return_value=fake_engine), patch(
            "echogtfs.services.database.base.async_sessionmaker", return_value=_Factory()
        ):
            repository = GtfsRepository("sqlite+aiosqlite://")
            await repository.initialize()
            await repository.close()

        fake_engine.dispose.assert_awaited_once()

    async def test_repository_is_single_instance(self):
        with patch("echogtfs.services.database.base.create_async_engine"), patch(
            "echogtfs.services.database.base.async_sessionmaker"
        ):
            first = GtfsRepository("sqlite+aiosqlite://")
            second = GtfsRepository("sqlite+aiosqlite://")

        self.assertIs(first, second)
