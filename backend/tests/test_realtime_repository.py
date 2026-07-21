from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.database.realtime_repository import RealtimeRepository


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestRealtimeRepository(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _make_repository(session):
        repository = object.__new__(RealtimeRepository)
        repository.get_session = lambda: _FakeSessionContext(session)
        return repository

    async def test_get_realtime_trips_returns_loaded_trips(self):
        trip = SimpleNamespace(id="trip-1")
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult([trip])))
        repository = self._make_repository(session)

        items = await repository.get_realtime_trips()

        self.assertEqual(items, [trip])
        session.execute.assert_awaited_once()

    async def test_get_realtime_trips_returns_empty_list(self):
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult([])))
        repository = self._make_repository(session)

        items = await repository.get_realtime_trips()

        self.assertEqual(items, [])
        session.execute.assert_awaited_once()

    async def test_get_realtime_vehicles_returns_loaded_vehicles(self):
        vehicle = SimpleNamespace(id="vehicle-1")
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult([vehicle])))
        repository = self._make_repository(session)

        items = await repository.get_realtime_vehicles()

        self.assertEqual(items, [vehicle])
        session.execute.assert_awaited_once()

    async def test_get_realtime_vehicles_returns_empty_list(self):
        session = SimpleNamespace(execute=AsyncMock(return_value=_FakeResult([])))
        repository = self._make_repository(session)

        items = await repository.get_realtime_vehicles()

        self.assertEqual(items, [])
        session.execute.assert_awaited_once()
