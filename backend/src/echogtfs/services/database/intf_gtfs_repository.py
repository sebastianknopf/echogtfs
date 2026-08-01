from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.services.database.models import GtfsAgency, GtfsRoute, GtfsStop, GtfsTrip


class GtfsRepositoryInterface(ABC):
    """Interface for GTFS static-table repository operations."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize repository resources and validate connectivity."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close repository resources."""
        raise NotImplementedError

    @abstractmethod
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a managed database session owned by the repository."""
        raise NotImplementedError

    @abstractmethod
    async def list_gtfs_entity_ids(self) -> dict[str, set[str]]:
        """Return GTFS entity IDs as sets for agency, route, stop, and trip."""
        raise NotImplementedError

    @abstractmethod
    async def list_gtfs_agencies(self) -> list[GtfsAgency]:
        """Return all GTFS agencies ordered by name."""
        raise NotImplementedError

    @abstractmethod
    async def list_gtfs_stops(self, *, query: str, limit: int) -> list[GtfsStop]:
        """Return GTFS stops filtered by query and limited by max rows."""
        raise NotImplementedError

    @abstractmethod
    async def list_gtfs_routes(self, *, query: str, limit: int) -> list[GtfsRoute]:
        """Return GTFS routes filtered by query and limited by max rows."""
        raise NotImplementedError

    @abstractmethod
    async def replace_gtfs_static_data(
        self,
        *,
        agencies: list[dict[str, str]],
        stops: list[dict[str, str]],
        routes: list[dict[str, str]],
    ) -> None:
        """Atomically replace all imported GTFS agencies, stops, and routes."""
        raise NotImplementedError

    @abstractmethod
    async def clear_gtfs_static_data(self) -> None:
        """Delete all imported GTFS static data in FK-safe order."""
        raise NotImplementedError

    @abstractmethod
    async def insert_gtfs_agencies(self, agencies: list[dict[str, str]]) -> None:
        """Insert GTFS agencies rows."""
        raise NotImplementedError

    @abstractmethod
    async def insert_gtfs_stops(self, stops: list[dict[str, str]]) -> None:
        """Insert GTFS stop rows."""
        raise NotImplementedError

    @abstractmethod
    async def insert_gtfs_routes(self, routes: list[dict[str, str]]) -> None:
        """Insert GTFS route rows."""
        raise NotImplementedError

    @abstractmethod
    async def insert_gtfs_trips(self, trips: list[dict[str, str | int | datetime]]) -> None:
        """Insert GTFS trip rows."""
        raise NotImplementedError

    @abstractmethod
    async def insert_gtfs_stop_times(self, stop_times: list[dict[str, str | int | datetime]]) -> None:
        """Insert GTFS stop-time rows."""
        raise NotImplementedError

    @abstractmethod
    async def find_trip_ids_by_match_properties(
        self,
        *,
        route_id: str | None = None,
        operation_day_date: date | None = None,
        scheduled_start_time: datetime | None = None,
        scheduled_end_time: datetime | None = None,
        scheduled_start_stop_id: str | None = None,
        scheduled_end_stop_id: str | None = None,
    ) -> list[str] | None:
        """Return GTFS trip IDs matching the provided trip properties."""
        raise NotImplementedError

    @abstractmethod
    async def get_gtfs_trip_with_stop_times(
        self,
        trip_id: str,
    ) -> GtfsTrip | None:
        """Return one GTFS trip with ordered stop_times relationship loaded."""
        raise NotImplementedError
