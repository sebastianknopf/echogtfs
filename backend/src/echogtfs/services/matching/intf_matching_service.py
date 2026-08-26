from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from echogtfs.enum.gtfsrt import AssignmentType


class MatchingServiceInterface(ABC):
    """Interface for matching realtime trip metadata to one GTFS trip ID."""

    @abstractmethod
    async def match(
        self,
        *,
        trip_id: str,
        route_id: str | None = None,
        operation_day_date: date | None = None,
        scheduled_start_time: datetime | None = None,
        scheduled_end_time: datetime | None = None,
        scheduled_start_stop_id: str | None = None,
        scheduled_end_stop_id: str | None = None,
        scheduled_intermediate_stops: list[tuple[str, datetime]] | None = None,
    ) -> tuple[str | None, AssignmentType]:
        """Return one matched GTFS trip ID with the assignment type describing the match.

        The trip ID is None when no unique match exists; the assignment type then
        describes why no trip was assigned.
        """
        raise NotImplementedError
