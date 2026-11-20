from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.database.system_repository import SystemRepository


class TestSqlAlchemyRepository(unittest.IsolatedAsyncioTestCase):
    async def test_list_differential_data_source_ids(self):
        result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [2, 4]))
        fake_session = SimpleNamespace(execute=AsyncMock(return_value=result))
        repository = SystemRepository.__new__(SystemRepository)

        class _SessionContext:
            async def __aenter__(self):
                return fake_session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with patch.object(repository, "get_session", return_value=_SessionContext()):
            ids = await repository.list_differential_data_source_ids()

        self.assertEqual(ids, [2, 4])
        fake_session.execute.assert_awaited_once()

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

        with patch("echogtfs.services.database.postgres_base.create_async_engine", return_value=fake_engine), patch(
            "echogtfs.services.database.postgres_base.async_sessionmaker", return_value=_Factory()
        ):
            repository = SystemRepository("sqlite+aiosqlite://")
            await repository.initialize()
            await repository.close()

        fake_engine.dispose.assert_awaited_once()