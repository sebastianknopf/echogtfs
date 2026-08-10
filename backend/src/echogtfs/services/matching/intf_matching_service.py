from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class MatchingServiceInterface(ABC):
    """Interface for matching realtime trip metadata to one GTFS trip ID."""

    @abstractmethod
    async def match(
        self,
        *,
        trip_id: str,
        route_id: str | None = None,
        scheduled_start_time: datetime | None = None,
        scheduled_end_time: datetime | None = None,
        scheduled_start_stop_id: str | None = None,
        scheduled_end_stop_id: str | None = None,
        scheduled_intermediate_stops: list[tuple[str, datetime]] | None = None,
    ) -> str | None:
        """Return one matched GTFS trip ID, or None when no unique match exists."""
        raise NotImplementedError
