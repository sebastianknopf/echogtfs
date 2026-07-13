from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from echogtfs.services.database.intf_repository import RepositoryInterface
from echogtfs.services.database.models import AppSetting, ServiceAlert, User


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

    async def get_app_setting(self, key: str) -> str | None:
        """Return one app setting value by key, or None if key is missing."""
        async with self.get_session() as db:
            row = await db.get(AppSetting, key)
            
            return row.value if row is not None else None

    async def set_app_setting(self, key: str, value: str) -> None:
        """Create or update one app setting and persist it immediately."""
        async with self.get_session() as db:
            row = await db.get(AppSetting, key)

            if row is None:
                db.add(AppSetting(key=key, value=value))
            else:
                row.value = value

            await db.commit()

    async def get_all_app_settings(self) -> dict[str, str]:
        """Return all app settings as a plain key-value mapping."""
        stmt = select(AppSetting)
        async with self.get_session() as db:
            result = await db.execute(stmt)

            return {row.key: row.value for row in result.scalars().all()}

    async def get_user_by_id(self, user_id: int) -> User | None:
        """Return one user by id, or None when not found."""
        async with self.get_session() as db:
            return await db.get(User, user_id)

    async def get_user_by_username(self, username: str) -> User | None:
        """Return one user by username, or None when not found."""
        stmt = select(User).where(User.username == username)
        async with self.get_session() as db:
            result = await db.execute(stmt)

            return result.scalar_one_or_none()

    async def user_exists_by_username_or_email(self, username: str, email: str) -> bool:
        """Return True when a user exists with the given username or email."""
        stmt = select(User.id).where((User.username == username) | (User.email == email)).limit(1)
        async with self.get_session() as db:
            result = await db.execute(stmt)

            return result.scalar_one_or_none() is not None

    async def list_users(self) -> list[User]:
        """Return all users ordered by creation time."""
        stmt = select(User).order_by(User.created_at)
        async with self.get_session() as db:
            result = await db.execute(stmt)

            return list(result.scalars().all())

    async def create_user(
        self,
        username: str,
        email: str,
        hashed_password: str,
        *,
        is_active: bool = True,
        is_superuser: bool = False,
        is_technical_contact: bool = False,
    ) -> User:
        """Create and persist one user."""
        async with self.get_session() as db:
            user = User(
                username=username,
                email=email,
                hashed_password=hashed_password,
                is_active=is_active,
                is_superuser=is_superuser,
                is_technical_contact=is_technical_contact,
            )

            db.add(user)
            await db.commit()
            await db.refresh(user)

            return user

    async def update_user(
        self,
        user_id: int,
        *,
        email: str | None = None,
        hashed_password: str | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
        is_technical_contact: bool | None = None,
    ) -> User | None:
        """Update mutable user fields and return updated user, or None when not found."""
        async with self.get_session() as db:
            user = await db.get(User, user_id)

            if user is None:
                return None

            if email is not None:
                user.email = email
            if hashed_password is not None:
                user.hashed_password = hashed_password
            if is_active is not None:
                user.is_active = is_active
            if is_superuser is not None:
                user.is_superuser = is_superuser
            if is_technical_contact is not None:
                user.is_technical_contact = is_technical_contact

            await db.commit()
            await db.refresh(user)

            return user

    async def delete_user(self, user_id: int) -> bool:
        """Delete one user by id. Returns True when a row was deleted."""
        async with self.get_session() as db:
            user = await db.get(User, user_id)

            if user is None:
                return False
            await db.delete(user)
            await db.commit()

            return True

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