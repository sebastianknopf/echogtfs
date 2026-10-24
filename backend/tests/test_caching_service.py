from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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

        await service.put_trip_id("external-trip-1", "T42")

        client.set.assert_awaited_once_with(
            "echogtfs:data:trips:external-trip-1",
            "T42",
            ex=24 * 60 * 60,
        )

    async def test_get_trip_id_returns_cached_value(self):
        service = CachingService("redis://redis:6379/0")
        client = SimpleNamespace(get=AsyncMock(return_value="T42"))
        service._client = client

        result = await service.get_trip_id("external-trip-1")

        self.assertEqual(result, "T42")
        client.get.assert_awaited_once_with("echogtfs:data:trips:external-trip-1")

    async def test_get_trip_id_returns_none_when_missing(self):
        service = CachingService("redis://redis:6379/0")
        client = SimpleNamespace(get=AsyncMock(return_value=None))
        service._client = client

        result = await service.get_trip_id("missing")

        self.assertIsNone(result)
        client.get.assert_awaited_once_with("echogtfs:data:trips:missing")

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
            await service.put_trip_id("external-trip-1", "T1")

    async def test_get_trip_id_raises_when_service_not_initialized(self):
        service = CachingService("redis://redis:6379/0")

        with self.assertRaises(RuntimeError):
            await service.get_trip_id("external-trip-1")

    async def test_pop_trip_id_raises_when_service_not_initialized(self):
        service = CachingService("redis://redis:6379/0")

        with self.assertRaises(RuntimeError):
            await service.pop_trip_id("external-trip-1")

    async def test_contains_gtfs_ids_returns_known_subset_in_one_pipeline(self):
        service = CachingService("redis://redis:6379/0")
        pipeline = SimpleNamespace(
            smismember=MagicMock(),
            exists=MagicMock(),
            execute=AsyncMock(return_value=[[1, 0], 1]),
        )
        service._client = SimpleNamespace(pipeline=MagicMock(return_value=pipeline))

        result = await service.contains_gtfs_ids("route", ["r1", "r2"])

        self.assertEqual(result, {"r1"})
        pipeline.smismember.assert_called_once_with("echogtfs:data:ids:route", ["r1", "r2"])
        pipeline.exists.assert_called_once_with("echogtfs:data:ids:meta:ready")

    async def test_contains_gtfs_ids_returns_none_when_cache_not_built(self):
        service = CachingService("redis://redis:6379/0")
        pipeline = SimpleNamespace(
            smismember=MagicMock(),
            exists=MagicMock(),
            execute=AsyncMock(return_value=[[1], 0]),
        )
        service._client = SimpleNamespace(pipeline=MagicMock(return_value=pipeline))

        self.assertIsNone(await service.contains_gtfs_ids("stop", ["s1"]))

    async def test_rebuild_gtfs_ids_swaps_temp_keys_atomically_and_releases_lock(self):
        service = CachingService("redis://redis:6379/0")
        pipeline = SimpleNamespace(
            delete=MagicMock(),
            rename=MagicMock(),
            set=MagicMock(),
            execute=AsyncMock(),
        )
        client = SimpleNamespace(
            set=AsyncMock(return_value=True),
            exists=AsyncMock(return_value=0),
            delete=AsyncMock(),
            sadd=AsyncMock(),
            pipeline=MagicMock(return_value=pipeline),
        )
        service._client = client
        gtfs_repository = SimpleNamespace(
            list_gtfs_entity_ids=AsyncMock(
                return_value={"agency": {"a1"}, "route": {"r1"}, "stop": set(), "trip": {"t1"}}
            )
        )

        await service.rebuild_gtfs_ids(gtfs_repository)

        gtfs_repository.list_gtfs_entity_ids.assert_awaited_once_with(kinds=("agency", "route", "stop", "trip"))
        client.pipeline.assert_called_once_with(transaction=True)
        pipeline.rename.assert_any_call("echogtfs:data:ids:agency:tmp", "echogtfs:data:ids:agency")
        pipeline.rename.assert_any_call("echogtfs:data:ids:route:tmp", "echogtfs:data:ids:route")
        pipeline.rename.assert_any_call("echogtfs:data:ids:trip:tmp", "echogtfs:data:ids:trip")
        pipeline.delete.assert_called_once_with("echogtfs:data:ids:stop")
        pipeline.set.assert_called_once_with("echogtfs:data:ids:meta:ready", "1")
        pipeline.execute.assert_awaited_once()
        client.delete.assert_awaited_with("echogtfs:data:ids:meta:lock")

    async def test_rebuild_gtfs_ids_skips_when_ready_and_not_forced(self):
        service = CachingService("redis://redis:6379/0")
        client = SimpleNamespace(
            set=AsyncMock(return_value=True),
            exists=AsyncMock(return_value=1),
            delete=AsyncMock(),
        )
        service._client = client
        gtfs_repository = SimpleNamespace(list_gtfs_entity_ids=AsyncMock())

        await service.rebuild_gtfs_ids(gtfs_repository, force=False)

        gtfs_repository.list_gtfs_entity_ids.assert_not_awaited()
        client.delete.assert_awaited_once_with("echogtfs:data:ids:meta:lock")
