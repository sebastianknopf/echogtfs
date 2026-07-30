from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

fake_redis_module = types.ModuleType("redis")
fake_redis_asyncio_module = types.ModuleType("redis.asyncio")


class _FakeRedisClient:
    @classmethod
    def from_url(cls, *_args, **_kwargs):
        return cls()


fake_redis_asyncio_module.Redis = _FakeRedisClient
fake_redis_module.asyncio = fake_redis_asyncio_module
sys.modules.setdefault("redis", fake_redis_module)
sys.modules.setdefault("redis.asyncio", fake_redis_asyncio_module)

from echogtfs.services.caching.caching_service import CachingService


class TestCachingService(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_creates_client_and_pings(self):
        service = CachingService("redis://redis:6379/0")
        client = SimpleNamespace(ping=AsyncMock())

        with patch(
            "echogtfs.services.caching.caching_service.Redis.from_url",
            return_value=client,
        ) as from_url_mock:
            await service.initialize()

        from_url_mock.assert_called_once_with(
            "redis://redis:6379/0",
            encoding="utf-8",
            decode_responses=True,
        )
        client.ping.assert_awaited_once()

    async def test_close_closes_client_and_resets_reference(self):
        service = CachingService("redis://redis:6379/0")
        client = SimpleNamespace(aclose=AsyncMock())
        service._client = client

        await service.close()

        client.aclose.assert_awaited_once()
        self.assertIsNone(service._client)

    async def test_put_trip_id_sets_expected_key_value_and_ttl(self):
        service = CachingService("redis://redis:6379/0")
        client = SimpleNamespace(set=AsyncMock())
        service._client = client

        await service.put_trip_id("external-trip-1", 42)

        client.set.assert_awaited_once_with(
            "echogtfs:data:trips:external-trip-1",
            "42",
            ex=24 * 60 * 60,
        )

    async def test_pop_trip_id_returns_true_when_key_deleted(self):
        service = CachingService("redis://redis:6379/0")
        client = SimpleNamespace(delete=AsyncMock(return_value=1))
        service._client = client

        result = await service.pop_trip_id("external-trip-1")

        self.assertTrue(result)
        client.delete.assert_awaited_once_with("echogtfs:data:trips:external-trip-1")

    async def test_pop_trip_id_returns_false_when_key_not_found(self):
        service = CachingService("redis://redis:6379/0")
        client = SimpleNamespace(delete=AsyncMock(return_value=0))
        service._client = client

        result = await service.pop_trip_id("missing")

        self.assertFalse(result)
        client.delete.assert_awaited_once_with("echogtfs:data:trips:missing")

    async def test_put_trip_id_raises_when_service_not_initialized(self):
        service = CachingService("redis://redis:6379/0")

        with self.assertRaises(RuntimeError):
            await service.put_trip_id("external-trip-1", 1)

    async def test_pop_trip_id_raises_when_service_not_initialized(self):
        service = CachingService("redis://redis:6379/0")

        with self.assertRaises(RuntimeError):
            await service.pop_trip_id("external-trip-1")
