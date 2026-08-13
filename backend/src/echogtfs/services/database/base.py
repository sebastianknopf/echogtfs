from __future__ import annotations

from collections.abc import AsyncGenerator
from contextvars import ContextVar
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


_current_session: ContextVar[tuple[object, AsyncSession] | None] = ContextVar(
    "echogtfs_current_database_session",
    default=None,
)


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
        current_context = _current_session.get()
        if current_context is not None and current_context[0] is self:
            yield current_context[1]
            return

        async with self._session_factory() as db:
            yield db

    @asynccontextmanager
    async def transaction(
        self,
        *,
        isolation_level: str | None = None,
    ) -> AsyncGenerator[AsyncSession, None]:
        """Run repository operations in one session and transaction."""
        current_context = _current_session.get()
        if current_context is not None and current_context[0] is self:
            yield current_context[1]
            return

        if not hasattr(self, "_session_factory"):
            async with self.get_session() as db:
                yield db
            return

        async with self._session_factory() as db:
            if isolation_level is not None:
                await db.connection(
                    execution_options={"isolation_level": isolation_level}
                )

            token = _current_session.set((self, db))
            try:
                try:
                    yield db
                except Exception:
                    await db.rollback()
                    raise
                else:
                    await db.commit()
            finally:
                _current_session.reset(token)

    async def commit(self, db: AsyncSession) -> None:
        """Commit standalone work, leaving an enclosing repository transaction open."""
        current_context = _current_session.get()
        if current_context is not None and current_context[0] is self and current_context[1] is db:
            return

        await db.commit()
