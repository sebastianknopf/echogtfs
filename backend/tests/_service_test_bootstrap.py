"""Shared singleton bootstrap for backend unit tests.

This module provides lightweight in-memory/default service singletons so tests
that instantiate datasource classes can run without full app startup.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

# Import echogtfs.common before echogtfs.services.security: security_service.py
# triggers echogtfs.common's own package init, which imports back from
# echogtfs.services.security, causing a circular-import error unless
# echogtfs.common is already fully initialized first.
import echogtfs.common  # noqa: F401

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
        self._gtfs_ids: dict[str, set[str]] = {}
        self._gtfs_ids_task: asyncio.Task | None = None

    async def put_trip_id(self, external_trip_id: str, internal_trip_id: str) -> None:
        self._trip_ids[str(external_trip_id)] = str(internal_trip_id)
        
    async def has_gtfs_ids(self) -> bool:
        return self._gtfs_ids_task is asyncio.current_task()

    async def contains_gtfs_ids(self, kind: str, gtfs_ids: list[str]) -> set[str] | None:
        # IDs are only valid inside the task that loaded them, so each test reloads from its own repository stub.
        if self._gtfs_ids_task is not asyncio.current_task():
            return None

        known_ids = self._gtfs_ids.get(kind, set())
        return {gtfs_id for gtfs_id in gtfs_ids if gtfs_id in known_ids}

    async def rebuild_gtfs_ids(self, gtfs_repository, force: bool = True) -> None:
        self._gtfs_ids = await gtfs_repository.list_gtfs_entity_ids(kinds=("agency", "route", "stop", "trip"))
        self._gtfs_ids_task = asyncio.current_task()

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
