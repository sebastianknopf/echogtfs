from __future__ import annotations

from abc import ABC, abstractmethod


class CachingServiceInterface(ABC):
    """Interface for trip ID cache operations."""

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
