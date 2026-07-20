from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.orm import selectinload

from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.database.models import (
    AppSetting,
    DataSource,
    DataSourceEnrichment,
    DataSourceLog,
    DataSourceMapping,
    ServiceAlert,
    ServiceAlertActivePeriod,
    ServiceAlertInformedEntity,
    ServiceAlertTranslation,
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
        log_file_uuid: uuid.UUID,
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
        stmt = select(DataSourceLog.log_file_uuid).where(DataSourceLog.data_source_id == data_source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return [row[0] for row in result.all()]

    async def delete_data_source_logs_for_data_source(self, data_source_id: int) -> int:
        """Delete all data source log rows for one data source and return affected row count."""
        stmt = delete(DataSourceLog).where(DataSourceLog.data_source_id == data_source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await db.commit()

            return int(result.rowcount or 0)

    async def list_data_source_log_uuids_before(self, cutoff_time: datetime) -> list[uuid.UUID]:
        """Return data source log file UUIDs older than cutoff time."""
        stmt = select(DataSourceLog.log_file_uuid).where(DataSourceLog.timestamp < cutoff_time)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return [row[0] for row in result.all()]

    async def delete_data_source_logs_before(self, cutoff_time: datetime) -> int:
        """Delete data source logs older than cutoff time and return affected row count."""
        stmt = delete(DataSourceLog).where(DataSourceLog.timestamp < cutoff_time)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await db.commit()

            return int(result.rowcount or 0)

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
    
    async def list_expired_internal_alert_ids(self, current_timestamp: int, *, only_active: bool) -> list[uuid.UUID]:
        """Return internal alert ids where all active periods already ended."""
        subquery = (
            select(ServiceAlertActivePeriod.alert_id)
            .group_by(ServiceAlertActivePeriod.alert_id)
            .having(
                func.max(ServiceAlertActivePeriod.end_time).isnot(None)
                & (func.max(ServiceAlertActivePeriod.end_time) < current_timestamp)
            )
        )

        stmt = select(ServiceAlert.id).where(
            ServiceAlert.data_source_id.is_(None),
            ServiceAlert.id.in_(subquery),
        )
        
        if only_active:
            stmt = stmt.where(ServiceAlert.is_active == True)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return [row[0] for row in result.all()]

    async def list_internal_alert_ids_expired_before(self, cutoff_timestamp: int) -> list[uuid.UUID]:
        """Return internal alert ids where all active periods ended before cutoff timestamp."""
        subquery = (
            select(ServiceAlertActivePeriod.alert_id)
            .group_by(ServiceAlertActivePeriod.alert_id)
            .having(
                func.max(ServiceAlertActivePeriod.end_time).isnot(None)
                & (func.max(ServiceAlertActivePeriod.end_time) < cutoff_timestamp)
            )
        )

        stmt = select(ServiceAlert.id).where(
            ServiceAlert.data_source_id.is_(None),
            ServiceAlert.id.in_(subquery),
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return [row[0] for row in result.all()]

    async def deactivate_service_alerts(self, alert_ids: list[uuid.UUID]) -> int:
        """Deactivate service alerts by id and return affected row count."""
        if not alert_ids:
            return 0

        stmt = update(ServiceAlert).where(ServiceAlert.id.in_(alert_ids)).values(is_active=False)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await db.commit()

            return int(result.rowcount or 0)

    async def delete_service_alerts_by_ids(self, alert_ids: list[uuid.UUID]) -> int:
        """Delete service alerts by id and return affected row count."""
        if not alert_ids:
            return 0

        stmt = delete(ServiceAlert).where(ServiceAlert.id.in_(alert_ids))

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

    async def list_service_alerts_for_data_source(self, source_id: int) -> list[ServiceAlert]:
        """Return alerts linked to one data source."""
        stmt = select(ServiceAlert).where(ServiceAlert.data_source_id == source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def list_service_alerts_paginated(
        self,
        *,
        page: int,
        limit: int,
        sort: str,
        search: str,
        is_active: bool | None,
        has_data_source: bool | None,
    ) -> tuple[list[ServiceAlert], int]:
        """Return paginated service alerts and total count with required relationships loaded."""
        page = max(1, page)
        limit = max(1, min(100, limit))
        offset = (page - 1) * limit
        normalized_sort = sort.lower() if sort in ["newest", "oldest"] else "newest"

        subq = (
            select(
                ServiceAlertActivePeriod.alert_id,
                func.min(ServiceAlertActivePeriod.start_time).label("first_start"),
            )
            .group_by(ServiceAlertActivePeriod.alert_id)
            .subquery()
        )

        where_conditions = []
        trimmed_search = search.strip()
        if trimmed_search:
            search_pattern = f"%{trimmed_search}%"
            where_conditions.append(
                ServiceAlert.id.in_(
                    select(ServiceAlertTranslation.alert_id)
                    .where(ServiceAlertTranslation.header_text.ilike(search_pattern))
                    .distinct()
                )
            )

        if is_active is not None:
            where_conditions.append(ServiceAlert.is_active == is_active)

        if has_data_source is not None:
            if has_data_source:
                where_conditions.append(ServiceAlert.data_source_id.is_not(None))
            else:
                where_conditions.append(ServiceAlert.data_source_id.is_(None))

        count_stmt = select(func.count(ServiceAlert.id))
        if where_conditions:
            count_stmt = count_stmt.where(*where_conditions)

        sort_expr = subq.c.first_start.desc() if normalized_sort == "newest" else subq.c.first_start.asc()

        stmt = select(ServiceAlert).outerjoin(subq, ServiceAlert.id == subq.c.alert_id)
        if where_conditions:
            stmt = stmt.where(*where_conditions)

        stmt = stmt.options(
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
            selectinload(ServiceAlert.data_source),
        ).order_by(
            case((subq.c.first_start.is_(None), 0), else_=1),
            sort_expr.nulls_last(),
        ).offset(offset).limit(limit)

        async with self.get_session() as db:
            count_result = await db.execute(count_stmt)
            total = int(count_result.scalar_one())

            result = await db.execute(stmt)
            items = list(result.scalars().all())
            return items, total

    async def get_service_alert_by_id_with_relations(self, alert_id: uuid.UUID) -> ServiceAlert | None:
        """Return one service alert by id with required relationships loaded."""
        stmt = (
            select(ServiceAlert)
            .where(ServiceAlert.id == alert_id)
            .options(
                selectinload(ServiceAlert.data_source),
                selectinload(ServiceAlert.translations),
                selectinload(ServiceAlert.active_periods),
                selectinload(ServiceAlert.informed_entities),
            )
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def create_service_alert(
        self,
        *,
        cause: str,
        effect: str,
        severity_level: str,
        is_active: bool,
        translations: list[dict[str, Any]],
        active_periods: list[dict[str, Any]],
        informed_entities: list[dict[str, Any]],
    ) -> ServiceAlert:
        """Create one internal service alert and return it with relationships loaded."""
        async with self.get_session() as db:
            alert = ServiceAlert(
                cause=cause,
                effect=effect,
                severity_level=severity_level,
                is_active=is_active,
            )
            db.add(alert)
            await db.flush()

            for translation_data in translations:
                db.add(ServiceAlertTranslation(alert_id=alert.id, **translation_data))

            for period_data in active_periods:
                db.add(ServiceAlertActivePeriod(alert_id=alert.id, **period_data))

            for entity_data in informed_entities:
                db.add(ServiceAlertInformedEntity(alert_id=alert.id, **entity_data))

            await db.commit()

            stmt = (
                select(ServiceAlert)
                .where(ServiceAlert.id == alert.id)
                .options(
                    selectinload(ServiceAlert.data_source),
                    selectinload(ServiceAlert.translations),
                    selectinload(ServiceAlert.active_periods),
                    selectinload(ServiceAlert.informed_entities),
                )
            )
            result = await db.execute(stmt)
            return result.scalar_one()

    async def update_service_alert(
        self,
        alert_id: uuid.UUID,
        *,
        cause: str | None = None,
        effect: str | None = None,
        severity_level: str | None = None,
        is_active: bool | None = None,
        translations: list[dict[str, Any]] | None = None,
        active_periods: list[dict[str, Any]] | None = None,
        informed_entities: list[dict[str, Any]] | None = None,
    ) -> ServiceAlert | None:
        """Update one service alert and optionally replace child rows."""
        stmt = (
            select(ServiceAlert)
            .where(ServiceAlert.id == alert_id)
            .options(
                selectinload(ServiceAlert.data_source),
                selectinload(ServiceAlert.translations),
                selectinload(ServiceAlert.active_periods),
                selectinload(ServiceAlert.informed_entities),
            )
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            alert = result.scalar_one_or_none()
            if alert is None:
                return None

            if cause is not None:
                alert.cause = cause
            if effect is not None:
                alert.effect = effect
            if severity_level is not None:
                alert.severity_level = severity_level
            if is_active is not None:
                alert.is_active = is_active

            if translations is not None:
                await db.execute(
                    delete(ServiceAlertTranslation).where(ServiceAlertTranslation.alert_id == alert_id)
                )
                for translation_data in translations:
                    db.add(ServiceAlertTranslation(alert_id=alert_id, **translation_data))

            if active_periods is not None:
                await db.execute(
                    delete(ServiceAlertActivePeriod).where(ServiceAlertActivePeriod.alert_id == alert_id)
                )
                for period_data in active_periods:
                    db.add(ServiceAlertActivePeriod(alert_id=alert_id, **period_data))

            if informed_entities is not None:
                await db.execute(
                    delete(ServiceAlertInformedEntity).where(ServiceAlertInformedEntity.alert_id == alert_id)
                )
                for entity_data in informed_entities:
                    db.add(ServiceAlertInformedEntity(alert_id=alert_id, **entity_data))

            await db.commit()

            refreshed = await db.execute(stmt)
            return refreshed.scalar_one_or_none()

    async def toggle_service_alert_active(self, alert_id: uuid.UUID) -> ServiceAlert | None:
        """Toggle the is_active flag for one service alert and return updated model."""
        stmt = (
            select(ServiceAlert)
            .where(ServiceAlert.id == alert_id)
            .options(
                selectinload(ServiceAlert.data_source),
                selectinload(ServiceAlert.translations),
                selectinload(ServiceAlert.active_periods),
                selectinload(ServiceAlert.informed_entities),
            )
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            alert = result.scalar_one_or_none()
            if alert is None:
                return None

            alert.is_active = not alert.is_active
            await db.commit()

            refreshed = await db.execute(stmt)
            return refreshed.scalar_one_or_none()

    async def list_service_alerts_by_ids(self, alert_ids: list[uuid.UUID]) -> list[ServiceAlert]:
        """Return alerts by IDs."""
        if not alert_ids:
            return []

        stmt = select(ServiceAlert).where(ServiceAlert.id.in_(alert_ids))

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def delete_service_alerts_for_data_source_by_ids(
        self,
        source_id: int,
        alert_ids: list[uuid.UUID],
    ) -> int:
        """Delete alerts by IDs only for the given data source."""
        if not alert_ids:
            return 0

        stmt = delete(ServiceAlert).where(
            ServiceAlert.data_source_id == source_id,
            ServiceAlert.id.in_(alert_ids),
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await db.commit()
            return int(result.rowcount or 0)

    async def upsert_service_alert_from_sync(
        self,
        *,
        alert_id: uuid.UUID,
        source_id: int,
        source_name: str,
        cause: str,
        effect: str,
        severity_level: str,
        is_active_on_create: bool,
        translations: list[dict[str, Any]],
        active_periods: list[dict[str, Any]],
        informed_entities: list[dict[str, Any]],
    ) -> str:
        """Create or update a synchronized alert and replace child records."""
        async with self.get_session() as db:
            existing = await db.get(ServiceAlert, alert_id)

            action = "updated"
            if existing is None:
                action = "created"
                existing = ServiceAlert(
                    id=alert_id,
                    cause=cause,
                    effect=effect,
                    severity_level=severity_level,
                    source=source_name,
                    data_source_id=source_id,
                    is_active=is_active_on_create,
                )
                db.add(existing)
                await db.flush()
            else:
                existing.cause = cause
                existing.effect = effect
                existing.severity_level = severity_level
                existing.source = source_name
                existing.data_source_id = source_id

            await db.execute(
                delete(ServiceAlertTranslation).where(ServiceAlertTranslation.alert_id == alert_id)
            )
            await db.execute(
                delete(ServiceAlertActivePeriod).where(ServiceAlertActivePeriod.alert_id == alert_id)
            )
            await db.execute(
                delete(ServiceAlertInformedEntity).where(ServiceAlertInformedEntity.alert_id == alert_id)
            )

            for translation_data in translations:
                db.add(ServiceAlertTranslation(alert_id=alert_id, **translation_data))

            for period_data in active_periods:
                db.add(ServiceAlertActivePeriod(alert_id=alert_id, **period_data))

            for entity_data in informed_entities:
                db.add(ServiceAlertInformedEntity(alert_id=alert_id, **entity_data))

            await db.commit()
            return action