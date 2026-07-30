from __future__ import annotations

import logging

from redis.asyncio import Redis

from echogtfs.services.caching.intf_caching_service import CachingServiceInterface

logger = logging.getLogger("uvicorn")


class CachingService(CachingServiceInterface):
    """Single-instance Redis-backed cache for short-lived trip ID mappings."""

    _TRIP_KEY_PREFIX = "echogtfs:data:trips"
    _TRIP_CACHE_TTL_SECONDS = 24 * 60 * 60

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

    async def put_trip_id(self, external_trip_id: str, internal_trip_id: int) -> None:
        client = self._get_client()

        key = self._build_trip_key(external_trip_id)
        await client.set(key, str(internal_trip_id), ex=self._TRIP_CACHE_TTL_SECONDS)

    async def pop_trip_id(self, external_trip_id: str) -> bool:
        client = self._get_client()

        key = self._build_trip_key(external_trip_id)
        deleted_count = await client.delete(key)
        return deleted_count > 0

    def _get_client(self) -> Redis:
        if self._client is None:
            raise RuntimeError("Caching service is not initialized")

        return self._client
