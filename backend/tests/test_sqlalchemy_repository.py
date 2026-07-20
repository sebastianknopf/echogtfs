from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.database.sqlalchemy_repository import SqlAlchemyRepository


class TestSqlAlchemyRepository(unittest.IsolatedAsyncioTestCase):
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

        with patch("echogtfs.services.database.sqlalchemy_repository.create_async_engine", return_value=fake_engine), patch(
            "echogtfs.services.database.sqlalchemy_repository.async_sessionmaker", return_value=_Factory()
        ):
            repository = SqlAlchemyRepository("sqlite+aiosqlite://")
            await repository.initialize()
            await repository.close()

        fake_engine.dispose.assert_awaited_once()