from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, insert, select, text

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
        """Return GTFS IDs for agency, route, and stop as sets."""
        async with self.get_session() as db:
            agencies_result = await db.execute(select(GtfsAgency.gtfs_id))
            routes_result = await db.execute(select(GtfsRoute.gtfs_id))
            stops_result = await db.execute(select(GtfsStop.gtfs_id))

            return {
                "agency": {row[0] for row in agencies_result.fetchall()},
                "route": {row[0] for row in routes_result.fetchall()},
                "stop": {row[0] for row in stops_result.fetchall()},
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
