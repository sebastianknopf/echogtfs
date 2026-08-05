from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


class RepositoryBase:
    """Shared async SQLAlchemy engine/session lifecycle for repositories."""

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
