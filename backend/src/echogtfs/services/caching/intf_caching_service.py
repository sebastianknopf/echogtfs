from __future__ import annotations

from abc import ABC, abstractmethod

from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface


class CachingServiceInterface(ABC):
    """Interface for trip ID and nominal GTFS ID cache operations."""

    @abstractmethod
    async def initialize(self) -> None:
        """Validate Redis connectivity and prepare the cache service."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release cache service resources on application shutdown."""
        raise NotImplementedError

    @abstractmethod
    async def put_trip_id(self, external_trip_id: str, internal_trip_id: str) -> None:
        """Store one external->internal trip ID match with TTL."""
        raise NotImplementedError

    @abstractmethod
    async def get_trip_id(self, external_trip_id: str) -> str | None:
        """Return one cached internal trip ID by external trip ID, or None when missing."""
        raise NotImplementedError

    @abstractmethod
    async def pop_trip_id(self, external_trip_id: str) -> bool:
        """Delete cached trip mapping and return True when one entry was deleted."""
        raise NotImplementedError

    @abstractmethod
    async def has_gtfs_ids(self) -> bool:
        """Return True when the nominal GTFS ID cache is fully built."""
        raise NotImplementedError

    @abstractmethod
    async def contains_gtfs_ids(self, kind: str, gtfs_ids: list[str]) -> set[str] | None:
        """Return the subset of gtfs_ids known for kind (agency, route, stop), or None when the cache is not built."""
        raise NotImplementedError

    @abstractmethod
    async def rebuild_gtfs_ids(self, gtfs_repository: GtfsRepositoryInterface, force: bool = True) -> None:
        """Atomically replace the nominal GTFS ID cache with the current database content.

        With force=False the rebuild is skipped when the cache is already built.
        """
        raise NotImplementedError
