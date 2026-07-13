from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from echogtfs.services.database.intf_repository import RepositoryInterface
from echogtfs.services.database.models import (
    AppSetting,
    DataSource,
    DataSourceEnrichment,
    DataSourceLog,
    DataSourceMapping,
    ServiceAlert,
    User,
)


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

    async def list_data_sources(self) -> list[DataSource]:
        """Return all data sources ordered by name with relationships loaded."""
        stmt = (
            select(DataSource)
            .options(
                selectinload(DataSource.mappings),
                selectinload(DataSource.enrichments),
            )
            .order_by(DataSource.name)
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def get_data_source_by_id(self, source_id: int) -> DataSource | None:
        """Return one data source by id with relationships loaded."""
        stmt = (
            select(DataSource)
            .where(DataSource.id == source_id)
            .options(
                selectinload(DataSource.mappings),
                selectinload(DataSource.enrichments),
            )
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def get_data_source_by_name(self, name: str) -> DataSource | None:
        """Return one data source by name."""
        stmt = select(DataSource).where(DataSource.name == name)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def data_source_name_exists(self, name: str, *, exclude_id: int | None = None) -> bool:
        """Return True when a data source with the given name exists."""
        stmt = select(DataSource.id).where(DataSource.name == name)
        if exclude_id is not None:
            stmt = stmt.where(DataSource.id != exclude_id)
        stmt = stmt.limit(1)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def create_data_source(
        self,
        *,
        name: str,
        source_type: str,
        config: str,
        cron: str | None,
        is_active: bool,
        invalid_reference_policy: str,
        mappings: list[dict[str, str]],
        enrichments: list[dict[str, str | int]],
    ) -> DataSource:
        """Create one data source including mappings and enrichments."""
        async with self.get_session() as db:
            source = DataSource(
                name=name,
                type=source_type,
                config=config,
                cron=cron,
                is_active=is_active,
                invalid_reference_policy=invalid_reference_policy,
            )
            db.add(source)
            await db.flush()

            for mapping_data in mappings:
                db.add(
                    DataSourceMapping(
                        data_source_id=source.id,
                        entity_type=mapping_data["entity_type"],
                        key=mapping_data["key"],
                        value=mapping_data["value"],
                    )
                )

            for enrichment_data in enrichments:
                db.add(
                    DataSourceEnrichment(
                        data_source_id=source.id,
                        enrichment_type=enrichment_data["enrichment_type"],
                        source_field=enrichment_data["source_field"],
                        key=enrichment_data["key"],
                        value=enrichment_data["value"],
                        sort_order=int(enrichment_data["sort_order"]),
                    )
                )

            await db.commit()

            stmt = (
                select(DataSource)
                .where(DataSource.id == source.id)
                .options(
                    selectinload(DataSource.mappings),
                    selectinload(DataSource.enrichments),
                )
            )
            
            result = await db.execute(stmt)

            return result.scalar_one()

    async def update_data_source(
        self,
        source_id: int,
        *,
        name: str | None = None,
        source_type: str | None = None,
        config: str | None = None,
        cron: str | None = None,
        is_active: bool | None = None,
        invalid_reference_policy: str | None = None,
        mappings: list[dict[str, str]] | None = None,
        enrichments: list[dict[str, str | int]] | None = None,
    ) -> DataSource | None:
        """Update one data source and optionally replace mappings/enrichments."""
        stmt = (
            select(DataSource)
            .where(DataSource.id == source_id)
            .options(
                selectinload(DataSource.mappings),
                selectinload(DataSource.enrichments),
            )
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            source = result.scalar_one_or_none()
            if source is None:
                return None

            if name is not None:
                source.name = name
            if source_type is not None:
                source.type = source_type
            if config is not None:
                source.config = config
            if cron is not None:
                source.cron = cron
            if is_active is not None:
                source.is_active = is_active
            if invalid_reference_policy is not None:
                source.invalid_reference_policy = invalid_reference_policy

            if mappings is not None:
                for mapping in source.mappings:
                    await db.delete(mapping)
                for mapping_data in mappings:
                    db.add(
                        DataSourceMapping(
                            data_source_id=source.id,
                            entity_type=mapping_data["entity_type"],
                            key=mapping_data["key"],
                            value=mapping_data["value"],
                        )
                    )

            if enrichments is not None:
                for enrichment in source.enrichments:
                    await db.delete(enrichment)
                for enrichment_data in enrichments:
                    db.add(
                        DataSourceEnrichment(
                            data_source_id=source.id,
                            enrichment_type=enrichment_data["enrichment_type"],
                            source_field=enrichment_data["source_field"],
                            key=enrichment_data["key"],
                            value=enrichment_data["value"],
                            sort_order=int(enrichment_data["sort_order"]),
                        )
                    )

            await db.commit()

            refreshed = await db.execute(stmt)

            return refreshed.scalar_one_or_none()

    async def toggle_data_source_active(self, source_id: int) -> DataSource | None:
        """Toggle active state for one data source and return updated model."""
        stmt = (
            select(DataSource)
            .where(DataSource.id == source_id)
            .options(
                selectinload(DataSource.mappings),
                selectinload(DataSource.enrichments),
            )
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            source = result.scalar_one_or_none()
            if source is None:
                return None

            source.is_active = not source.is_active
            await db.commit()

            refreshed = await db.execute(stmt)

            return refreshed.scalar_one_or_none()

    async def delete_data_source(self, source_id: int) -> DataSource | None:
        """Delete one data source and return deleted model snapshot."""
        stmt = select(DataSource).where(DataSource.id == source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            source = result.scalar_one_or_none()
            if source is None:
                return None

            await db.delete(source)
            await db.commit()

            return source

    async def delete_alerts_for_data_source(self, source_id: int) -> int:
        """Delete all alerts for one data source and return deleted row count."""
        stmt = delete(ServiceAlert).where(ServiceAlert.data_source_id == source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)

            await db.commit()

            return int(result.rowcount or 0)

    async def update_service_alert_source_name(self, old_name: str, new_name: str) -> None:
        """Rename service alert source text."""
        stmt = update(ServiceAlert).where(ServiceAlert.source == old_name).values(source=new_name)

        async with self.get_session() as db:
            await db.execute(stmt)
            await db.commit()

    async def list_data_source_mappings(self, source_id: int, entity_type: str) -> list[DataSourceMapping]:
        """Return mappings for one source and entity type."""
        stmt = (
            select(DataSourceMapping)
            .where(
                DataSourceMapping.data_source_id == source_id,
                DataSourceMapping.entity_type == entity_type,
            )
            .order_by(DataSourceMapping.key)
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def replace_data_source_mappings_for_entity_type(
        self,
        source_id: int,
        entity_type: str,
        mappings: list[dict[str, str]],
    ) -> int:
        """Replace mappings for one source and entity type."""
        async with self.get_session() as db:
            await db.execute(
                delete(DataSourceMapping).where(
                    DataSourceMapping.data_source_id == source_id,
                    DataSourceMapping.entity_type == entity_type,
                )
            )

            for mapping_data in mappings:
                db.add(
                    DataSourceMapping(
                        data_source_id=source_id,
                        entity_type=entity_type,
                        key=mapping_data["key"],
                        value=mapping_data["value"],
                    )
                )

            await db.commit()

            return len(mappings)

    async def get_latest_data_source_log(self, source_id: int) -> DataSourceLog | None:
        """Return latest log entry for a data source."""
        stmt = (
            select(DataSourceLog)
            .where(DataSourceLog.data_source_id == source_id)
            .order_by(DataSourceLog.timestamp.desc())
            .limit(1)
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def list_data_source_logs(self, source_id: int, limit: int) -> list[DataSourceLog]:
        """Return recent log entries for a data source."""
        stmt = (
            select(DataSourceLog)
            .where(DataSourceLog.data_source_id == source_id)
            .order_by(DataSourceLog.timestamp.desc())
            .limit(limit)
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def get_data_source_log_by_id(self, log_id: int) -> DataSourceLog | None:
        """Return one data source log entry by id."""
        stmt = select(DataSourceLog).where(DataSourceLog.id == log_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        
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