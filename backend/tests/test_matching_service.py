from __future__ import annotations

import os
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")

from echogtfs.matching.matching_service import MatchingService


class TestMatchingService(unittest.IsolatedAsyncioTestCase):
    async def test_match_returns_cached_trip_id_without_querying_repository(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T1"]))
        caching_service = SimpleNamespace(
            get_trip_id=AsyncMock(return_value="CACHED-T42"),
            put_trip_id=AsyncMock(),
        )
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(result, "CACHED-T42")
        caching_service.get_trip_id.assert_awaited_once_with("external-trip-1")
        repository.find_trip_ids_by_match_properties.assert_not_awaited()
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_returns_none_when_route_id_missing(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T1"]))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id=None,
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        )

        self.assertIsNone(result)
        caching_service.get_trip_id.assert_awaited_once_with("external-trip-1")
        repository.find_trip_ids_by_match_properties.assert_not_awaited()
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_returns_none_when_start_time_missing(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T1"]))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=None,
        )

        self.assertIsNone(result)
        caching_service.get_trip_id.assert_awaited_once_with("external-trip-1")
        repository.find_trip_ids_by_match_properties.assert_not_awaited()
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_returns_unique_trip_id(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T42"]))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
            scheduled_end_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            scheduled_start_stop_id="de:123:stopA:platform1",
            scheduled_end_stop_id="de:123:stopB:platform2",
        )

        self.assertEqual(result, "T42")
        caching_service.get_trip_id.assert_awaited_once_with("external-trip-1")
        repository.find_trip_ids_by_match_properties.assert_awaited_once_with(
            route_id="R1",
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
            scheduled_end_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            scheduled_start_stop_id="de:123:stopA",
            scheduled_end_stop_id="de:123:stopB",
        )
        caching_service.put_trip_id.assert_awaited_once_with("external-trip-1", "T42")

    async def test_match_returns_none_for_no_match(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=None))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        )

        self.assertIsNone(result)
        caching_service.put_trip_id.assert_not_awaited()

    async def test_match_returns_none_for_ambiguous_match(self):
        repository = SimpleNamespace(find_trip_ids_by_match_properties=AsyncMock(return_value=["T1", "T2"]))
        caching_service = SimpleNamespace(get_trip_id=AsyncMock(return_value=None), put_trip_id=AsyncMock())
        service = MatchingService(repository, caching_service)

        result = await service.match(
            trip_id="external-trip-1",
            route_id="R1",
            scheduled_start_time=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        )

        self.assertIsNone(result)
        caching_service.put_trip_id.assert_not_awaited()
