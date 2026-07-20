from __future__ import annotations

from sqlalchemy import delete, insert, select

from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.models import GtfsAgency, GtfsRoute, GtfsStop
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
        async with self.get_session() as db:
            await db.execute(delete(GtfsAgency))
            await db.execute(delete(GtfsStop))
            await db.execute(delete(GtfsRoute))

            if agencies:
                await db.execute(insert(GtfsAgency), agencies)
            if stops:
                await db.execute(insert(GtfsStop), stops)
            if routes:
                await db.execute(insert(GtfsRoute), routes)

            await db.commit()
