from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from datetime import date
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

    async def test_clear_and_insert_methods_execute_and_commit(self):
        fake_engine = SimpleNamespace(dispose=AsyncMock())

        class _FakeSession:
            def __init__(self) -> None:
                self.execute = AsyncMock()
                self.commit = AsyncMock()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_session = _FakeSession()

        class _Factory:
            def __call__(self):
                return fake_session

        with patch("echogtfs.services.database.base.create_async_engine", return_value=fake_engine), patch(
            "echogtfs.services.database.base.async_sessionmaker", return_value=_Factory()
        ):
            repository = GtfsRepository("sqlite+aiosqlite://")
            await repository.clear_gtfs_static_data()
            await repository.insert_gtfs_agencies([{"gtfs_id": "A", "name": "Agency"}])
            await repository.insert_gtfs_stops([{"gtfs_id": "S", "name": "Stop"}])
            await repository.insert_gtfs_routes([{"gtfs_id": "R", "short_name": "R", "long_name": "Route"}])
            await repository.insert_gtfs_trips(
                [
                    {
                        "gtfs_id": "T1",
                        "route_id": "R",
                        "direction_id": 0,
                        "start_time": datetime(1970, 1, 1, 8, 0, 0, tzinfo=UTC),
                        "start_stop_id": "S",
                        "end_time": datetime(1970, 1, 1, 9, 0, 0, tzinfo=UTC),
                        "end_stop_id": "S",
                    }
                ]
            )
            await repository.insert_gtfs_stop_times(
                [
                    {
                        "trip_id": "T1",
                        "stop_id": "S",
                        "stop_sequence": 1,
                        "arrival_time": datetime(1970, 1, 1, 8, 0, 0, tzinfo=UTC),
                        "departure_time": datetime(1970, 1, 1, 8, 0, 0, tzinfo=UTC),
                    }
                ]
            )

        self.assertGreaterEqual(fake_session.execute.await_count, 6)
        self.assertGreaterEqual(fake_session.commit.await_count, 6)

    async def test_list_gtfs_object_statistics_returns_counts(self):
        fake_engine = SimpleNamespace(dispose=AsyncMock())

        class _CountResult:
            def __init__(self, count: int) -> None:
                self._count = count

            def scalar_one(self) -> int:
                return self._count

        class _FakeSession:
            def __init__(self) -> None:
                self.execute = AsyncMock(
                    side_effect=[
                        _CountResult(1),
                        _CountResult(2),
                        _CountResult(3),
                        _CountResult(4),
                    ]
                )

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_session = _FakeSession()

        class _Factory:
            def __call__(self):
                return fake_session

        with patch("echogtfs.services.database.base.create_async_engine", return_value=fake_engine), patch(
            "echogtfs.services.database.base.async_sessionmaker", return_value=_Factory()
        ):
            repository = GtfsRepository("sqlite+aiosqlite://")
            result = await repository.list_gtfs_object_statistics()

        self.assertEqual(
            result,
            {
                "num_agencies": 1,
                "num_routes": 2,
                "num_stops": 3,
                "num_trips": 4,
            },
        )
        self.assertEqual(fake_session.execute.await_count, 4)

    async def test_list_gtfs_operation_day_dates_returns_distinct_dates(self):
        fake_engine = SimpleNamespace(dispose=AsyncMock())

        class _ScalarsResult:
            def __init__(self, values: list[date]) -> None:
                self._values = values

            def scalars(self):
                return self

            def all(self) -> list[date]:
                return self._values

        class _FakeSession:
            def __init__(self) -> None:
                self.execute = AsyncMock(
                    return_value=_ScalarsResult([date(2026, 8, 20), date(2026, 8, 21)])
                )

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_session = _FakeSession()

        class _Factory:
            def __call__(self):
                return fake_session

        with patch("echogtfs.services.database.base.create_async_engine", return_value=fake_engine), patch(
            "echogtfs.services.database.base.async_sessionmaker", return_value=_Factory()
        ):
            repository = GtfsRepository("sqlite+aiosqlite://")
            result = await repository.list_gtfs_operation_day_dates()

        self.assertEqual(result, [date(2026, 8, 20), date(2026, 8, 21)])
        fake_session.execute.assert_awaited_once()
