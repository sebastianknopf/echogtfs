from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from echogtfs.common.global_id import GlobalId
from echogtfs.services.matching.intf_matching_service import MatchingServiceInterface
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
        operation_day_date: date | None = None,
        scheduled_start_time: datetime | None = None,
        scheduled_end_time: datetime | None = None,
        scheduled_start_stop_id: str | None = None,
        scheduled_end_stop_id: str | None = None,
        scheduled_intermediate_stops: list[tuple[str, datetime]] | None = None,
    ) -> str | None:
        """Return one matched GTFS trip ID, or None when no unique match exists."""
        cached_trip_id = await self._caching_service.get_trip_id(trip_id)
        if cached_trip_id is not None:
            return cached_trip_id

        if route_id is None:
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

        internal_trip_id = await self._match_by_start_end_anchors(
            route_id=route_id,
            operation_day_date=operation_day_date,
            scheduled_start_time=scheduled_start_time,
            scheduled_end_time=scheduled_end_time,
            scheduled_start_stop_id=reduced_start_stop_id,
            scheduled_end_stop_id=reduced_end_stop_id,
        )

        if internal_trip_id is not None:
            await self._caching_service.put_trip_id(trip_id, internal_trip_id)
            return internal_trip_id

        use_intermediate_fallback = (
            scheduled_start_time is None
            and scheduled_end_time is None
            and bool(scheduled_intermediate_stops)
        )

        if not use_intermediate_fallback:
            return None

        reduced_intermediate_stops = self._reduce_intermediate_stops(scheduled_intermediate_stops)
        if not reduced_intermediate_stops:
            return None

        internal_trip_id = await self._match_by_intermediate_stops(
            route_id=route_id,
            operation_day_date=operation_day_date,
            scheduled_intermediate_stops=reduced_intermediate_stops,
        )

        if internal_trip_id is None:
            return None

        await self._caching_service.put_trip_id(trip_id, internal_trip_id)
        return internal_trip_id

    async def _match_by_start_end_anchors(
        self,
        *,
        route_id: str,
        operation_day_date: date | None,
        scheduled_start_time: datetime | None,
        scheduled_end_time: datetime | None,
        scheduled_start_stop_id: str | None,
        scheduled_end_stop_id: str | None,
    ) -> str | None:
        if scheduled_start_time is None:
            return None

        trip_ids = await self._repository.find_trip_ids_by_match_properties(
            route_id=route_id,
            operation_day_date=operation_day_date or scheduled_start_time.date(),
            scheduled_start_time=scheduled_start_time,
            scheduled_end_time=scheduled_end_time,
            scheduled_start_stop_id=scheduled_start_stop_id,
            scheduled_end_stop_id=scheduled_end_stop_id,
        )

        if not trip_ids or len(trip_ids) != 1:
            return None

        return trip_ids[0]

    async def _match_by_intermediate_stops(
        self,
        *,
        route_id: str,
        operation_day_date: date | None,
        scheduled_intermediate_stops: list[tuple[str, datetime]],
    ) -> str | None:
        candidate_trip_ids = await self._repository.find_trip_ids_by_match_properties(
            route_id=route_id,
            operation_day_date=operation_day_date,
        )
        
        if not candidate_trip_ids:
            return None

        matched_trip_ids: list[str] = []
        for candidate_trip_id in candidate_trip_ids:
            gtfs_trip = await self._repository.get_gtfs_trip_with_stop_times(candidate_trip_id)
            if gtfs_trip is None:
                continue

            matches = await asyncio.to_thread(
                self._trip_matches_intermediate_stops,
                gtfs_trip,
                scheduled_intermediate_stops,
            )
            if matches:
                matched_trip_ids.append(candidate_trip_id)

        if len(matched_trip_ids) != 1:
            return None

        return matched_trip_ids[0]

    @staticmethod
    def _reduce_intermediate_stops(
        scheduled_intermediate_stops: list[tuple[str, datetime]],
    ) -> list[tuple[str, datetime]]:
        reduced: list[tuple[str, datetime]] = []
        for stop_id, stop_time in scheduled_intermediate_stops:
            if not stop_id or not isinstance(stop_time, datetime):
                continue

            reduced.append((GlobalId.level(stop_id, 3), stop_time))

        return reduced

    def _trip_matches_intermediate_stops(
        self,
        gtfs_trip: Any,
        scheduled_intermediate_stops: list[tuple[str, datetime]],
    ) -> bool:
        stop_times = getattr(gtfs_trip, "stop_times", None)
        if not isinstance(stop_times, list) or not stop_times:
            return False

        for stop_id, scheduled_time in scheduled_intermediate_stops:
            if not self._has_matching_stop_time(stop_times, stop_id, scheduled_time):
                return False

        return True

    def _has_matching_stop_time(
        self,
        stop_times: list[Any],
        reduced_stop_id: str,
        scheduled_time: datetime,
    ) -> bool:
        for stop_time in stop_times:
            candidate_stop_id = getattr(stop_time, "stop_id", None)
            departure_time = getattr(stop_time, "departure_time", None)
            if not isinstance(candidate_stop_id, str) or departure_time is None:
                continue

            if not candidate_stop_id.startswith(reduced_stop_id):
                continue

            departure_time_utc = self._to_utc(departure_time)
            scheduled_time_utc = self._to_utc(scheduled_time)
            if departure_time_utc is None or scheduled_time_utc is None:
                continue

            if abs(departure_time_utc - scheduled_time_utc) <= timedelta(seconds=60):
                return True

        return False

    @staticmethod
    def _to_utc(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)