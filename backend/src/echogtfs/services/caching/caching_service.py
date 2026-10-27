from __future__ import annotations

import asyncio
import logging
import time

from redis.asyncio import Redis

from echogtfs.services.caching.intf_caching_service import CachingServiceInterface
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface

logger = logging.getLogger("uvicorn")


class CachingService(CachingServiceInterface):
    """Single-instance Redis-backed cache for trip ID mappings and nominal GTFS IDs."""

    _TRIP_KEY_PREFIX = "echogtfs:data:trips"
    _TRIP_CACHE_TTL_SECONDS = 24 * 60 * 60

    _GTFS_IDS_PREFIX = "echogtfs:data:ids"
    _GTFS_IDS_READY_KEY = "echogtfs:data:ids:meta:ready"
    _GTFS_IDS_LOCK_KEY = "echogtfs:data:ids:meta:lock"
    _GTFS_IDS_LOCK_TTL_SECONDS = 600
    _GTFS_IDS_LOCK_WAIT_SECONDS = 600
    _GTFS_IDS_CHUNK_SIZE = 10000
    _GTFS_ID_KINDS = ("agency", "route", "stop", "trip")

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client: Redis | None = None

    @staticmethod
    def _build_trip_key(external_trip_id: str) -> str:
        return f"{CachingService._TRIP_KEY_PREFIX}:{external_trip_id}"

    async def initialize(self) -> None:
        self._client = Redis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

        await self._client.ping()
        logger.info("[CachingService] Redis cache connection verified")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def put_trip_id(self, external_trip_id: str, internal_trip_id: str) -> None:
        client = self._get_client()

        key = self._build_trip_key(external_trip_id)
        await client.set(key, internal_trip_id, ex=self._TRIP_CACHE_TTL_SECONDS)

    async def get_trip_id(self, external_trip_id: str) -> str | None:
        client = self._get_client()

        key = self._build_trip_key(external_trip_id)
        value = await client.get(key)

        if value is None:
            return None

        return str(value)

    async def pop_trip_id(self, external_trip_id: str) -> bool:
        client = self._get_client()

        key = self._build_trip_key(external_trip_id)
        deleted_count = await client.delete(key)
        
        return deleted_count > 0

    def _get_client(self) -> Redis:
        if self._client is None:
            raise RuntimeError("Caching service is not initialized")

        return self._client

    @staticmethod
    def _build_gtfs_ids_key(kind: str) -> str:
        return f"{CachingService._GTFS_IDS_PREFIX}:{kind}"

    async def has_gtfs_ids(self) -> bool:
        client = self._get_client()

        return bool(await client.exists(self._GTFS_IDS_READY_KEY))

    async def contains_gtfs_ids(self, kind: str, gtfs_ids: list[str]) -> set[str] | None:
        client = self._get_client()

        pipeline = client.pipeline(transaction=False)
        if gtfs_ids:
            pipeline.smismember(self._build_gtfs_ids_key(kind), gtfs_ids)
        pipeline.exists(self._GTFS_IDS_READY_KEY)
        results = await pipeline.execute()

        # The marker is checked in the same round trip so a partially built cache is never trusted.
        if not results[-1]:
            return None

        if not gtfs_ids:
            return set()

        return {gtfs_id for gtfs_id, is_member in zip(gtfs_ids, results[0]) if is_member}

    async def rebuild_gtfs_ids(self, gtfs_repository: GtfsRepositoryInterface, force: bool = True) -> None:
        client = self._get_client()

        deadline = time.monotonic() + self._GTFS_IDS_LOCK_WAIT_SECONDS
        while not await client.set(self._GTFS_IDS_LOCK_KEY, "1", nx=True, ex=self._GTFS_IDS_LOCK_TTL_SECONDS):
            if time.monotonic() >= deadline:
                raise RuntimeError("Timed out waiting for the GTFS ID cache rebuild lock")

            await asyncio.sleep(0.25)

        try:
            if not force and await client.exists(self._GTFS_IDS_READY_KEY):
                return

            gtfs_ids = await gtfs_repository.list_gtfs_entity_ids(kinds=self._GTFS_ID_KINDS)

            temp_keys: dict[str, str | None] = {}
            for kind in self._GTFS_ID_KINDS:
                values = list(gtfs_ids.get(kind, set()))
                temp_key = f"{self._build_gtfs_ids_key(kind)}:tmp"
                await client.delete(temp_key)

                for start in range(0, len(values), self._GTFS_IDS_CHUNK_SIZE):
                    await client.sadd(temp_key, *values[start:start + self._GTFS_IDS_CHUNK_SIZE])

                temp_keys[kind] = temp_key if values else None

            # Readers see either the previous or the new complete cache, never a partial one.
            pipeline = client.pipeline(transaction=True)
            for kind, temp_key in temp_keys.items():
                if temp_key is None:
                    pipeline.delete(self._build_gtfs_ids_key(kind))
                else:
                    pipeline.rename(temp_key, self._build_gtfs_ids_key(kind))
            pipeline.set(self._GTFS_IDS_READY_KEY, "1")
            await pipeline.execute()

            logger.info(
                "[CachingService] GTFS ID cache rebuilt: "
                + ", ".join(f"{len(gtfs_ids.get(kind, set()))} {kind}s" for kind in self._GTFS_ID_KINDS)
            )
        finally:
            await client.delete(self._GTFS_IDS_LOCK_KEY)
