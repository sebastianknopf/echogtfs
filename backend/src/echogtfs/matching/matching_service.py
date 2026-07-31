from __future__ import annotations

from datetime import datetime

from echogtfs.common.global_id import GlobalId
from echogtfs.matching.intf_matching_service import MatchingServiceInterface
from echogtfs.services.caching import CachingServiceInterface
from echogtfs.services.database import GtfsRepositoryInterface


class MatchingService(MatchingServiceInterface):
    """Match realtime trip metadata to a unique GTFS trip ID."""

    def __init__(
        self,
        repository: GtfsRepositoryInterface,
        caching_service: CachingServiceInterface,
    ) -> None:
        self._repository = repository
        self._caching_service = caching_service

    async def match(
        self,
        *,
        trip_id: str,
        route_id: str | None = None,
        scheduled_start_time: datetime | None = None,
        scheduled_end_time: datetime | None = None,
        scheduled_start_stop_id: str | None = None,
        scheduled_end_stop_id: str | None = None,
    ) -> str | None:
        """Return one matched GTFS trip ID, or None when no unique match exists."""
        cached_trip_id = await self._caching_service.get_trip_id(trip_id)
        if cached_trip_id is not None:
            return cached_trip_id

        if route_id is None or scheduled_start_time is None:
            return None

        reduced_start_stop_id = (
            GlobalId.level(scheduled_start_stop_id, 3)
            if scheduled_start_stop_id is not None
            else None
        )
        reduced_end_stop_id = (
            GlobalId.level(scheduled_end_stop_id, 3)
            if scheduled_end_stop_id is not None
            else None
        )

        trip_ids = await self._repository.find_trip_ids_by_match_properties(
            route_id=route_id,
            scheduled_start_time=scheduled_start_time,
            scheduled_end_time=scheduled_end_time,
            scheduled_start_stop_id=reduced_start_stop_id,
            scheduled_end_stop_id=reduced_end_stop_id,
        )

        if not trip_ids or len(trip_ids) != 1:
            return None

        internal_trip_id = trip_ids[0]
        await self._caching_service.put_trip_id(trip_id, internal_trip_id)

        return internal_trip_id