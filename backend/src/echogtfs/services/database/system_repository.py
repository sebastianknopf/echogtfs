from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import case, delete, select, func, update
from sqlalchemy.orm import contains_eager, selectinload

from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.database.models import (
    AppSetting,
    DataSource,
    DataSourceEnrichment,
    DataSourceLog,
    DataSourceMapping,
    User,
)
from echogtfs.services.database.base import RepositoryBase


class SystemRepository(RepositoryBase, SystemRepositoryInterface):
    """SQLAlchemy-based repository for database access."""

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

    async def list_app_settings(self) -> list[AppSetting]:
        """Return all app setting rows ordered by key."""
        stmt = select(AppSetting).order_by(AppSetting.key)
        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

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

    async def list_active_data_sources_with_cron(self) -> list[DataSource]:
        """Return active data sources that have a cron expression configured."""
        stmt = (
            select(DataSource)
            .where(
                DataSource.cron.isnot(None),
                DataSource.is_active == True,
            )
            .order_by(DataSource.name)
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def list_data_sources_with_failures(self, min_num_failures: int = 0) -> list[DataSource]:
        """Return all data sources with at least the given number of failures ordered by name."""
        ranked_logs = (
            select(
                DataSourceLog.data_source_id.label("data_source_id"),
                DataSourceLog.status_code.label("status_code"),
                func.row_number()
                .over(
                    partition_by=DataSourceLog.data_source_id,
                    order_by=(
                        DataSourceLog.timestamp.desc(),
                        DataSourceLog.id.desc(),
                    ),
                )
                .label("rn"),
            )
            .subquery()
        )

        stmt = (
            select(DataSource)
            .outerjoin(DataSource.logs)
            .options(
                contains_eager(DataSource.logs),
            )
        )

        if min_num_failures > 0:
            failing_data_sources = (
                select(ranked_logs.c.data_source_id)
                .where(ranked_logs.c.rn <= min_num_failures)
                .group_by(ranked_logs.c.data_source_id)
                .having(
                    func.count(ranked_logs.c.data_source_id) >= min_num_failures,
                    func.sum(
                        case(
                            (ranked_logs.c.status_code != 200, 1),
                            else_=0,
                        )
                    ) == min_num_failures,
                )
            )

            stmt = stmt.where(
                DataSource.id.in_(failing_data_sources)
            )

        stmt = stmt.order_by(
            DataSource.name,
            DataSourceLog.timestamp.desc(),
            DataSourceLog.id.desc(),
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.unique().scalars().all())

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
        log_dumps: bool,
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
                log_dumps=log_dumps,
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
        log_dumps: bool | None = None,
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
            if log_dumps is not None:
                source.log_dumps = log_dumps
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

    async def update_data_source_last_run_at(self, source_id: int, last_run_at: datetime) -> bool:
        """Persist the last_run_at timestamp for one data source."""
        stmt = (
            update(DataSource)
            .where(DataSource.id == source_id)
            .values(last_run_at=last_run_at)
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await db.commit()

            return bool(result.rowcount)

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

    async def list_data_source_mappings_grouped(self, source_id: int) -> dict[str, dict[str, str]]:
        """Return mappings grouped by entity type for one data source."""
        stmt = select(DataSourceMapping).where(DataSourceMapping.data_source_id == source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            mappings = result.scalars().all()

            grouped: dict[str, dict[str, str]] = {}
            for mapping in mappings:
                grouped.setdefault(mapping.entity_type, {})[mapping.key] = mapping.value
            return grouped

    async def list_all_data_source_mappings(self) -> list[DataSourceMapping]:
        """Return all data source mappings ordered by id."""
        stmt = select(DataSourceMapping).order_by(DataSourceMapping.id)
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

    async def list_data_source_enrichments(self, source_id: int) -> list[dict[str, Any]]:
        """Return enrichments for one data source sorted by sort_order."""
        stmt = (
            select(DataSourceEnrichment)
            .where(DataSourceEnrichment.data_source_id == source_id)
            .order_by(DataSourceEnrichment.sort_order)
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            enrichments = result.scalars().all()

            return [
                {
                    "enrichment_type": enrichment.enrichment_type,
                    "source_field": enrichment.source_field,
                    "key": enrichment.key,
                    "value": enrichment.value,
                }
                for enrichment in enrichments
            ]

    async def list_all_data_source_enrichments(self) -> list[DataSourceEnrichment]:
        """Return all data source enrichments ordered by id."""
        stmt = select(DataSourceEnrichment).order_by(DataSourceEnrichment.id)
        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

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

    async def create_data_source_log(
        self,
        *,
        data_source_id: int,
        timestamp: datetime,
        request_url: str,
        request_headers: str | None,
        response_headers: str | None,
        response_mimetype: str | None,
        status_code: int | None,
        response_size: int,
        log_file_uuid: uuid.UUID | None,
    ) -> DataSourceLog:
        """Create one data source log entry and return persisted model."""
        async with self.get_session() as db:
            log_entry = DataSourceLog(
                data_source_id=data_source_id,
                timestamp=timestamp,
                request_url=request_url,
                request_headers=request_headers,
                response_headers=response_headers,
                response_mimetype=response_mimetype,
                status_code=status_code,
                response_size=response_size,
                log_file_uuid=log_file_uuid,
            )
            db.add(log_entry)
            await db.commit()
            await db.refresh(log_entry)

            return log_entry

    async def list_data_source_log_uuids_for_data_source(self, data_source_id: int) -> list[uuid.UUID]:
        """Return data source log file UUIDs for one data source."""
        stmt = select(DataSourceLog.log_file_uuid).where(
            DataSourceLog.data_source_id == data_source_id,
            DataSourceLog.log_file_uuid.is_not(None),
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def delete_data_source_logs_for_data_source(self, data_source_id: int) -> int:
        """Delete all data source log rows for one data source and return affected row count."""
        stmt = delete(DataSourceLog).where(DataSourceLog.data_source_id == data_source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await db.commit()

            return int(result.rowcount or 0)

    async def list_data_source_log_uuids_before(self, cutoff_time: datetime) -> list[uuid.UUID]:
        """Return data source log file UUIDs older than cutoff time."""
        stmt = select(DataSourceLog.log_file_uuid).where(
            DataSourceLog.timestamp < cutoff_time,
            DataSourceLog.log_file_uuid.is_not(None),
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def delete_data_source_logs_before(self, cutoff_time: datetime) -> int:
        """Delete data source logs older than cutoff time and return affected row count."""
        stmt = delete(DataSourceLog).where(DataSourceLog.timestamp < cutoff_time)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await db.commit()

            return int(result.rowcount or 0)

    async def get_data_source_invalid_reference_policy(self, source_id: int) -> str:
        """Return invalid reference policy configured for a data source."""
        stmt = select(DataSource.invalid_reference_policy).where(DataSource.id == source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            policy = result.scalar_one_or_none()
            if policy is None:
                raise ValueError(f"Data source {source_id} not found")
            return policy.value if hasattr(policy, "value") else str(policy)
