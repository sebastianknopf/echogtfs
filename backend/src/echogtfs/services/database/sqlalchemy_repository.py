from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from echogtfs.services.database.intf_repository import RepositoryInterface
from echogtfs.services.database.models import ServiceAlert


class SqlAlchemyRepository(RepositoryInterface):
    """SQLAlchemy-based repository for database access."""

    def __init__(self, database_url: str, debug: bool = False):
        self._engine: AsyncEngine = create_async_engine(database_url, echo=debug)
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
        )

    async def initialize(self) -> None:
        """Validate database connectivity during application startup."""
        async with self.get_session() as db:
            await db.execute(text("SELECT 1"))

    async def close(self) -> None:
        """Dispose repository-owned engine resources."""
        await self._engine.dispose()

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a managed session using repository-owned session factory."""
        async with self._session_factory() as db:
            yield db

    async def get_realtime_service_alerts(self) -> list[ServiceAlert]:
        """Return active realtime alerts with relationships needed for GTFS-RT export."""
        stmt = (
            select(ServiceAlert)
            .where(ServiceAlert.is_active == True)
            .options(
                selectinload(ServiceAlert.translations),
                selectinload(ServiceAlert.active_periods),
                selectinload(ServiceAlert.informed_entities),
            )
            .order_by(ServiceAlert.id)
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())
