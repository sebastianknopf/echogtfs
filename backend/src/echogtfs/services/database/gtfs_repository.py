from __future__ import annotations

from datetime import date, timedelta
from datetime import datetime

from sqlalchemy import delete, insert, select, text
from sqlalchemy.orm import selectinload

from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.models import GtfsAgency, GtfsRoute, GtfsStop, GtfsStopTime, GtfsTrip
from echogtfs.services.database.base import RepositoryBase


class GtfsRepository(RepositoryBase, GtfsRepositoryInterface):
    """SQLAlchemy repository for GTFS static-table operations."""

    _instance: GtfsRepository | None = None

    def __new__(cls, database_url: str, debug: bool = False) -> GtfsRepository:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        
        return cls._instance

    def __init__(self, database_url: str, debug: bool = False):
        if getattr(self, "_initialized", False):
            return

        super().__init__(database_url, debug)
        self._initialized = True

    async def list_gtfs_entity_ids(self) -> dict[str, set[str]]:
        """Return GTFS IDs for agency, route, stop, and trip as sets."""
        async with self.get_session() as db:
            agencies_result = await db.execute(select(GtfsAgency.gtfs_id))
            routes_result = await db.execute(select(GtfsRoute.gtfs_id))
            stops_result = await db.execute(select(GtfsStop.gtfs_id))
            trips_result = await db.execute(select(GtfsTrip.gtfs_id))

            return {
                "agency": {row[0] for row in agencies_result.fetchall()},
                "route": {row[0] for row in routes_result.fetchall()},
                "stop": {row[0] for row in stops_result.fetchall()},
                "trip": {row[0] for row in trips_result.fetchall()},
            }

    async def list_gtfs_agencies(self) -> list[GtfsAgency]:
        """Return all GTFS agencies ordered by name."""
        stmt = select(GtfsAgency).order_by(GtfsAgency.name)
        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def list_gtfs_stops(self, *, query: str, limit: int) -> list[GtfsStop]:
        """Return GTFS stops filtered by query and limited by max rows."""
        stmt = select(GtfsStop).order_by(GtfsStop.name)
        if query:
            stmt = stmt.where(
                GtfsStop.gtfs_id.ilike(f"%{query}%") | GtfsStop.name.ilike(f"%{query}%")
            )
        stmt = stmt.limit(limit)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def list_gtfs_routes(self, *, query: str, limit: int) -> list[GtfsRoute]:
        """Return GTFS routes filtered by query and limited by max rows."""
        stmt = select(GtfsRoute).order_by(GtfsRoute.short_name, GtfsRoute.long_name)
        if query:
            stmt = stmt.where(
                GtfsRoute.gtfs_id.ilike(f"%{query}%")
                | GtfsRoute.short_name.ilike(f"%{query}%")
                | GtfsRoute.long_name.ilike(f"%{query}%")
            )
        stmt = stmt.limit(limit)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def replace_gtfs_static_data(
        self,
        *,
        agencies: list[dict[str, str]],
        stops: list[dict[str, str]],
        routes: list[dict[str, str]],
    ) -> None:
        """Atomically replace all imported GTFS static entities."""
        await self.clear_gtfs_static_data()
        await self.insert_gtfs_agencies(agencies)
        await self.insert_gtfs_stops(stops)
        await self.insert_gtfs_routes(routes)

    async def clear_gtfs_static_data(self) -> None:
        """Delete all imported GTFS static data in FK-safe order. Use TRUNCATE to force deletion."""
        async with self.get_session() as db:
            tables = [
                GtfsStopTime.__table__.fullname,
                GtfsTrip.__table__.fullname,
                GtfsAgency.__table__.fullname,
                GtfsStop.__table__.fullname,
                GtfsRoute.__table__.fullname,
            ]

            sql = f"""
                TRUNCATE TABLE
                    {", ".join(tables)}
                RESTART IDENTITY CASCADE
            """

            async with self.get_session() as db:
                await db.execute(text(sql))
                await db.commit()

    async def insert_gtfs_agencies(self, agencies: list[dict[str, str]]) -> None:
        """Insert GTFS agencies rows."""
        if not agencies:
            return

        async with self.get_session() as db:
            await db.execute(insert(GtfsAgency), agencies)
            await db.commit()

    async def insert_gtfs_stops(self, stops: list[dict[str, str]]) -> None:
        """Insert GTFS stop rows."""
        if not stops:
            return

        async with self.get_session() as db:
            await db.execute(insert(GtfsStop), stops)
            await db.commit()

    async def insert_gtfs_routes(self, routes: list[dict[str, str]]) -> None:
        """Insert GTFS route rows."""
        if not routes:
            return

        async with self.get_session() as db:
            await db.execute(insert(GtfsRoute), routes)
            await db.commit()

    async def insert_gtfs_trips(self, trips: list[dict[str, str | int | datetime]]) -> None:
        """Insert GTFS trip rows."""
        if not trips:
            return

        async with self.get_session() as db:
            await db.execute(insert(GtfsTrip), trips)
            await db.commit()

    async def insert_gtfs_stop_times(self, stop_times: list[dict[str, str | int | datetime]]) -> None:
        """Insert GTFS stop-time rows."""
        if not stop_times:
            return

        async with self.get_session() as db:
            await db.execute(insert(GtfsStopTime), stop_times)
            await db.commit()

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
        """Return GTFS trip IDs using tolerant time and prefix stop matching rules."""
        stmt = select(GtfsTrip.gtfs_id)

        if route_id is not None:
            stmt = stmt.where(GtfsTrip.route_id == route_id)

        if operation_day_date is not None:
            stmt = stmt.where(GtfsTrip.operation_day_date == operation_day_date)

        if scheduled_start_time is not None:
            stmt = stmt.where(GtfsTrip.start_time >= (scheduled_start_time - timedelta(seconds=60)))
            stmt = stmt.where(GtfsTrip.start_time <= (scheduled_start_time + timedelta(seconds=60)))

        if scheduled_end_time is not None:
            stmt = stmt.where(GtfsTrip.end_time >= (scheduled_end_time - timedelta(seconds=60)))
            stmt = stmt.where(GtfsTrip.end_time <= (scheduled_end_time + timedelta(seconds=60)))

        if scheduled_start_stop_id is not None:
            stmt = stmt.where(GtfsTrip.start_stop_id.like(f"{scheduled_start_stop_id}%"))

        if scheduled_end_stop_id is not None:
            stmt = stmt.where(GtfsTrip.end_stop_id.like(f"{scheduled_end_stop_id}%"))

        stmt = stmt.order_by(GtfsTrip.gtfs_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            matches = list(result.scalars().all())
            return matches if matches else None

    async def get_gtfs_trip_with_stop_times(
        self,
        trip_id: str,
    ) -> GtfsTrip | None:
        """Return one GTFS trip with ordered stop_times relationship loaded."""
        stmt = (
            select(GtfsTrip)
            .where(GtfsTrip.gtfs_id == trip_id)
            .options(selectinload(GtfsTrip.stop_times))
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
