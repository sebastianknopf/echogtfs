"""Shared singleton bootstrap for backend unit tests.

This module provides lightweight in-memory/default service singletons so tests
that instantiate datasource classes can run without full app startup.
"""

from __future__ import annotations

from types import SimpleNamespace

from echogtfs.services.caching import set_caching_service
from echogtfs.services.database import (
    set_gtfs_repository,
    set_realtime_repository,
    set_system_repository,
)
from echogtfs.services.security import set_security_service


class _InMemoryCachingService:
    """Minimal async cache implementation used by tests."""

    def __init__(self) -> None:
        self._trip_ids: dict[str, str] = {}

    async def put_trip_id(self, external_trip_id: str, internal_trip_id: str) -> None:
        self._trip_ids[str(external_trip_id)] = str(internal_trip_id)

    async def get_trip_id(self, external_trip_id: str) -> str | None:
        return self._trip_ids.get(str(external_trip_id))

    async def pop_trip_id(self, external_trip_id: str) -> bool:
        key = str(external_trip_id)
        if key not in self._trip_ids:
            return False

        self._trip_ids.pop(key)
        return True


set_caching_service(_InMemoryCachingService())

# Provide harmless defaults for other global service singletons that some test
# imports may access before explicit patching.
_default_repo = SimpleNamespace()
set_system_repository(_default_repo)
set_gtfs_repository(_default_repo)
set_realtime_repository(_default_repo)
set_security_service(SimpleNamespace())
