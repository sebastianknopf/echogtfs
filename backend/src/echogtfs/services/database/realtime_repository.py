from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from echogtfs.enum.gtfsrt import AssignmentType
from sqlalchemy import case, delete, exists, func, select, update
from sqlalchemy.orm import selectinload

from echogtfs.services.database.base import RepositoryBase
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.models import (
    GtfsTrip,
    ServiceAlert,
    ServiceAlertActivePeriod,
    ServiceAlertInformedEntity,
    ServiceAlertTranslation,
    StopEvent,
    Trip,
    Vehicle,
)


class RealtimeRepository(RepositoryBase, RealtimeRepositoryInterface):
    """SQLAlchemy repository for realtime-table access."""

    async def delete_alerts_for_data_source(self, source_id: int) -> int:
        """Delete all alerts for one data source and return deleted row count."""
        stmt = delete(ServiceAlert).where(ServiceAlert.data_source_id == source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await self.commit(db)

            return int(result.rowcount or 0)

    async def update_service_alert_source_name(self, old_name: str, new_name: str) -> None:
        """Rename service alert source text."""
        stmt = update(ServiceAlert).where(ServiceAlert.source == old_name).values(source=new_name)

        async with self.get_session() as db:
            await db.execute(stmt)
            await self.commit(db)

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

        async with self.transaction(isolation_level="REPEATABLE READ") as db:
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
            await self.commit(db)

            return int(result.rowcount or 0)

    async def delete_service_alerts_by_ids(self, alert_ids: list[uuid.UUID]) -> int:
        """Delete service alerts by id and return affected row count."""
        if not alert_ids:
            return 0

        stmt = delete(ServiceAlert).where(ServiceAlert.id.in_(alert_ids))

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await self.commit(db)

            return int(result.rowcount or 0)

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

            await self.commit(db)

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

            await self.commit(db)

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
            await self.commit(db)

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
            await self.commit(db)
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

            await self.commit(db)
            return action

    async def get_realtime_trips(self) -> list[Trip]:
        """Return active realtime trips with relationships needed for GTFS-RT export."""
        stmt = (
            select(Trip)
            .where(Trip.is_active == True)
            .options(
                selectinload(Trip.data_source),
                selectinload(Trip.stop_events),
                selectinload(Trip.vehicle),
            )
            .order_by(Trip.created_at, Trip.trip_id)
        )

        async with self.transaction(isolation_level="REPEATABLE READ") as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def list_trips_paginated(
        self,
        *,
        page: int,
        limit: int,
        sort: str,
        search: str,
        is_active: bool | None,
    ) -> tuple[list[Trip], int]:
        """Return paginated realtime trips with required relationships loaded."""
        page = max(1, page)
        limit = max(1, min(100, limit))
        offset = (page - 1) * limit
        normalized_sort = sort.lower() if sort in ["asc", "desc"] else "asc"

        where_conditions = []
        trimmed_search = search.strip()
        if trimmed_search:
            search_pattern = f"%{trimmed_search}%"
            where_conditions.append(
                (
                    Trip.trip_id.ilike(search_pattern)
                    | Trip.route_id.ilike(search_pattern)
                    | Trip.start_date.ilike(search_pattern)
                    | Trip.start_time.ilike(search_pattern)
                )
            )

        if is_active is not None:
            where_conditions.append(Trip.is_active == is_active)

        count_stmt = select(func.count(Trip.id)).where(
            exists(select(StopEvent.trip_id).where(StopEvent.trip_id == Trip.trip_id))
        )
        if where_conditions:
            count_stmt = count_stmt.where(*where_conditions)

        sort_date = Trip.start_date.desc() if normalized_sort == "desc" else Trip.start_date.asc()
        sort_time = Trip.start_time.desc() if normalized_sort == "desc" else Trip.start_time.asc()

        stmt = select(Trip).where(
            exists(select(StopEvent.trip_id).where(StopEvent.trip_id == Trip.trip_id))
        )
        if where_conditions:
            stmt = stmt.where(*where_conditions)

        stmt = stmt.options(
            selectinload(Trip.data_source),
            selectinload(Trip.stop_events),
            selectinload(Trip.vehicle),
        ).order_by(
            sort_date,
            sort_time,
            Trip.trip_id.asc(),
        ).offset(offset).limit(limit)

        async with self.get_session() as db:
            count_result = await db.execute(count_stmt)
            total = int(count_result.scalar_one())

            result = await db.execute(stmt)
            items = list(result.scalars().all())
            return items, total

    async def list_trip_ids_with_invalid_stop_events(self, trip_ids: list[str]) -> set[str]:
        """Return trip_ids where at least one realtime stop event is marked invalid."""
        if not trip_ids:
            return set()

        stmt = (
            select(StopEvent.trip_id)
            .where(
                StopEvent.trip_id.in_(trip_ids),
                StopEvent.is_valid == False,
            )
            .distinct()
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return {row[0] for row in result.all()}

    async def toggle_trip_active(self, trip_uuid: uuid.UUID) -> Trip | None:
        """Toggle the is_active flag for one realtime trip and return updated model."""
        stmt = (
            select(Trip)
            .where(Trip.id == trip_uuid)
            .options(
                selectinload(Trip.data_source),
                selectinload(Trip.stop_events),
                selectinload(Trip.vehicle),
            )
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            trip = result.scalar_one_or_none()
            if trip is None:
                return None

            trip.is_active = not trip.is_active
            await self.commit(db)

            refreshed = await db.execute(stmt)
            return refreshed.scalar_one_or_none()

    async def delete_trips_for_data_source(self, source_id: int) -> int:
        """Delete all realtime trips for one data source and return deleted row count."""
        stmt = delete(Trip).where(Trip.data_source_id == source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await self.commit(db)

            return int(result.rowcount or 0)

    async def list_trips_for_data_source(self, source_id: int) -> list[Trip]:
        """Return realtime trips linked to one data source."""
        stmt = select(Trip).where(Trip.data_source_id == source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def list_trips_by_ids(self, trip_ids: list[uuid.UUID]) -> list[Trip]:
        """Return realtime trips by IDs."""
        if not trip_ids:
            return []

        stmt = select(Trip).where(Trip.id.in_(trip_ids))

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def list_trips_by_trip_ids(self, trip_ids: list[str]) -> list[Trip]:
        """Return realtime trips by trip_id values."""
        if not trip_ids:
            return []

        stmt = select(Trip).where(Trip.trip_id.in_(trip_ids))

        async with self.get_session() as db:
            result = await db.execute(stmt)

            return list(result.scalars().all())

    async def list_trip_ids_with_stop_events(self, trip_ids: list[str]) -> set[str]:
        """Return trip_id values that have at least one realtime stop event."""
        if not trip_ids:
            return set()

        stmt = select(StopEvent.trip_id).where(StopEvent.trip_id.in_(trip_ids)).distinct()

        async with self.get_session() as db:
            result = await db.execute(stmt)
            
            return {str(value) for value in result.scalars().all()}

    async def delete_trips_by_trip_ids(self, trip_ids: list[str]) -> int:
            """Delete realtime trip rows by trip_id and return the deleted row count."""
            if not trip_ids:
                return 0
    
            stmt = delete(Trip).where(Trip.trip_id.in_(trip_ids))
    
            async with self.get_session() as db:
                result = await db.execute(stmt)
                await self.commit(db)
                return int(result.rowcount or 0)

    async def delete_trips_for_data_source_by_ids(
        self,
        source_id: int,
        trip_ids: list[uuid.UUID],
    ) -> int:
        """Delete trips by IDs only for the given data source."""
        if not trip_ids:
            return 0

        stmt = delete(Trip).where(
            Trip.data_source_id == source_id,
            Trip.id.in_(trip_ids),
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await self.commit(db)
            return int(result.rowcount or 0)

    async def update_trip_update_from_sync(
        self,
        *,
        trip_uuid: uuid.UUID,
        source_id: int,
        source_name: str,
        trip_id: str,
        start_time: str,
        start_date: str,
        route_id: str,
        schedule_relationship: str,
        assignment_type: str,
        is_active_on_create: bool,
        is_trip_valid: bool,
        is_route_valid: bool,
        stop_events: list[dict[str, Any]],
        original_trip_id: str | None = None,
        scheduled_start_stop_id: str | None = None,
        scheduled_end_stop_id: str | None = None,
        scheduled_start_time: datetime | None = None,
        scheduled_end_time: datetime | None = None,
    ) -> str:
        """Create or update a synchronized trip update and replace stop events."""
        async with self.get_session() as db:
            existing = await db.get(Trip, trip_uuid)

            action = "updated"
            previous_trip_id = trip_id
            if existing is None:
                action = "created"
                existing = Trip(
                    id=trip_uuid,
                    data_source_id=source_id,
                    source=source_name,
                    trip_id=trip_id,
                    original_trip_id=original_trip_id,
                    scheduled_start_stop_id=scheduled_start_stop_id,
                    scheduled_end_stop_id=scheduled_end_stop_id,
                    scheduled_start_time=scheduled_start_time,
                    scheduled_end_time=scheduled_end_time,
                    start_time=start_time,
                    start_date=start_date,
                    route_id=route_id,
                    schedule_relationship=schedule_relationship,
                    assignment_type=assignment_type,
                    is_active=is_active_on_create,
                    is_trip_valid=is_trip_valid,
                    is_route_valid=is_route_valid,
                )

                db.add(existing)
                await db.flush()
            else:
                previous_trip_id = existing.trip_id
                existing.data_source_id = source_id
                existing.source = source_name
                existing.trip_id = trip_id
                existing.original_trip_id = original_trip_id
                existing.scheduled_start_stop_id = scheduled_start_stop_id
                existing.scheduled_end_stop_id = scheduled_end_stop_id
                existing.scheduled_start_time = scheduled_start_time
                existing.scheduled_end_time = scheduled_end_time
                existing.start_time = start_time
                existing.start_date = start_date
                existing.route_id = route_id
                existing.schedule_relationship = schedule_relationship

                if assignment_type != AssignmentType.MATCH_BY_CACHED_ID:
                    existing.assignment_type = assignment_type

                existing.is_trip_valid = is_trip_valid
                existing.is_route_valid = is_route_valid
                existing.updated_at = datetime.now(self._resolve_timezone(self._configured_timezone_name()))

            trip_ids_to_clear = [trip_id]
            if previous_trip_id != trip_id:
                trip_ids_to_clear.append(previous_trip_id)

            await db.execute(delete(StopEvent).where(StopEvent.trip_id.in_(trip_ids_to_clear)))

            for event_data in stop_events:
                payload = dict(event_data)
                payload.pop("trip_id", None)
                if payload.get("original_stop_id") in (None, ""):
                    payload["original_stop_id"] = payload.get("stop_id")

                payload["is_implied_schedule_relationship"] = bool(
                    payload.get("is_implied_schedule_relationship", False)
                )
                
                db.add(StopEvent(trip_id=trip_id, **payload))

            await self.commit(db)
            return action

    async def get_realtime_vehicles(self) -> list[Vehicle]:
        """Return active realtime vehicle positions with trip relations loaded."""
        stmt = (
            select(Vehicle)
            .where(Vehicle.is_active == True)
            .options(
                selectinload(Vehicle.trip),
            )
            .order_by(Vehicle.created_at, Vehicle.trip_id)
        )

        async with self.transaction(isolation_level="REPEATABLE READ") as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def list_vehicles_paginated(
        self,
        *,
        page: int,
        limit: int,
        search: str,
        is_active: bool | None,
    ) -> tuple[list[Vehicle], int]:
        """Return paginated realtime vehicles with required relationships loaded."""
        page = max(1, page)
        limit = max(1, min(1000, limit))
        offset = (page - 1) * limit

        where_conditions = []
        trimmed_search = search.strip()
        if trimmed_search:
            search_pattern = f"%{trimmed_search}%"
            where_conditions.append(
                (
                    Vehicle.vehicle_id.ilike(search_pattern)
                    | Vehicle.trip_id.ilike(search_pattern)
                    | Vehicle.vehicle_label.ilike(search_pattern)
                    | Vehicle.vehicle_license_plate.ilike(search_pattern)
                )
            )

        if is_active is not None:
            where_conditions.append(Vehicle.is_active == is_active)

        count_stmt = select(func.count(Vehicle.id))
        if where_conditions:
            count_stmt = count_stmt.where(*where_conditions)

        stmt = select(Vehicle)
        if where_conditions:
            stmt = stmt.where(*where_conditions)

        stmt = stmt.options(
            selectinload(Vehicle.data_source),
            selectinload(Vehicle.trip),
        ).order_by(
            Vehicle.timestamp.desc(),
            Vehicle.vehicle_id.asc(),
        ).offset(offset).limit(limit)

        async with self.get_session() as db:
            count_result = await db.execute(count_stmt)
            total = int(count_result.scalar_one())

            result = await db.execute(stmt)
            items = list(result.scalars().all())
            return items, total

    async def toggle_vehicle_active(self, vehicle_uuid: uuid.UUID) -> Vehicle | None:
        """Toggle the is_active flag for one realtime vehicle and return updated model."""
        stmt = (
            select(Vehicle)
            .where(Vehicle.id == vehicle_uuid)
            .options(
                selectinload(Vehicle.data_source),
                selectinload(Vehicle.trip),
            )
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            vehicle = result.scalar_one_or_none()
            if vehicle is None:
                return None

            vehicle.is_active = not vehicle.is_active
            await self.commit(db)

            refreshed = await db.execute(stmt)
            return refreshed.scalar_one_or_none()

    async def delete_vehicles_for_data_source(self, source_id: int) -> int:
        """Delete all realtime vehicles for one data source and return deleted row count."""
        stmt = delete(Vehicle).where(Vehicle.data_source_id == source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await self.commit(db)

            return int(result.rowcount or 0)

    async def list_vehicles_for_data_source(self, source_id: int) -> list[Vehicle]:
        """Return realtime vehicles linked to one data source."""
        stmt = select(Vehicle).where(Vehicle.data_source_id == source_id)

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def list_vehicles_by_ids(self, vehicle_ids: list[uuid.UUID]) -> list[Vehicle]:
        """Return realtime vehicles by IDs."""
        if not vehicle_ids:
            return []

        stmt = select(Vehicle).where(Vehicle.id.in_(vehicle_ids))

        async with self.get_session() as db:
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def delete_vehicles_for_data_source_by_ids(
        self,
        source_id: int,
        vehicle_ids: list[uuid.UUID],
    ) -> int:
        """Delete vehicles by IDs only for the given data source."""
        if not vehicle_ids:
            return 0

        stmt = delete(Vehicle).where(
            Vehicle.data_source_id == source_id,
            Vehicle.id.in_(vehicle_ids),
        )

        async with self.get_session() as db:
            result = await db.execute(stmt)
            await self.commit(db)
            return int(result.rowcount or 0)

    async def update_vehicle_position_from_sync(
        self,
        *,
        vehicle_uuid: uuid.UUID,
        source_id: int,
        source_name: str,
        trip_uuid: uuid.UUID,
        trip_id: str,
        trip_start_time: str,
        trip_start_date: str,
        trip_route_id: str,
        trip_schedule_relationship: str,
        trip_assignment_type: str,
        trip_is_active_on_create: bool,
        trip_is_trip_valid: bool,
        trip_is_route_valid: bool,
        vehicle_id: str,
        vehicle_label: str | None,
        vehicle_license_plate: str | None,
        vehicle_wheelchair_accessible: str,
        timestamp: Any,
        latitude: float,
        longitude: float,
        current_stop_sequence: int | None,
        current_status: str,
        assignment_type: str,
        congestion_level: str,
        is_active_on_create: bool,
        is_valid: bool,
    ) -> str:
        """Create or update a synchronized vehicle position and ensure linked trip exists."""
        async with self.get_session() as db:
            existing_trip = await db.get(Trip, trip_uuid)
            if existing_trip is None:
                existing_trip = Trip(
                    id=trip_uuid,
                    data_source_id=source_id,
                    source=source_name,
                    trip_id=trip_id,
                    start_time=trip_start_time,
                    start_date=trip_start_date,
                    route_id=trip_route_id,
                    schedule_relationship=trip_schedule_relationship,
                    assignment_type=trip_assignment_type,
                    is_active=trip_is_active_on_create,
                    is_trip_valid=trip_is_trip_valid,
                    is_route_valid=trip_is_route_valid,
                )
                
                db.add(existing_trip)
                await db.flush()

            existing_vehicle = await db.get(Vehicle, vehicle_uuid)

            action = "updated"
            if existing_vehicle is None:
                action = "created"
                existing_vehicle = Vehicle(
                    id=vehicle_uuid,
                    data_source_id=source_id,
                    source=source_name,
                    trip_id=trip_id,
                    vehicle_id=vehicle_id,
                    vehicle_label=vehicle_label,
                    vehicle_license_plate=vehicle_license_plate,
                    vehicle_wheelchair_accessible=vehicle_wheelchair_accessible,
                    timestamp=timestamp,
                    latitude=latitude,
                    longitude=longitude,
                    current_stop_sequence=current_stop_sequence,
                    current_status=current_status,
                    assignment_type=assignment_type,
                    congestion_level=congestion_level,
                    is_active=is_active_on_create,
                    is_valid=is_valid,
                )
                
                db.add(existing_vehicle)
                await db.flush()
            else:
                existing_vehicle.data_source_id = source_id
                existing_vehicle.source = source_name
                existing_vehicle.trip_id = trip_id
                existing_vehicle.vehicle_id = vehicle_id
                existing_vehicle.vehicle_label = vehicle_label
                existing_vehicle.vehicle_license_plate = vehicle_license_plate
                existing_vehicle.vehicle_wheelchair_accessible = vehicle_wheelchair_accessible
                existing_vehicle.timestamp = timestamp
                existing_vehicle.latitude = latitude
                existing_vehicle.longitude = longitude
                existing_vehicle.current_stop_sequence = current_stop_sequence
                existing_vehicle.current_status = current_status

                if assignment_type != AssignmentType.MATCH_BY_CACHED_ID:
                    existing_vehicle.assignment_type = assignment_type

                existing_vehicle.congestion_level = congestion_level
                existing_vehicle.is_valid = is_valid
                existing_vehicle.updated_at = datetime.now(self._resolve_timezone(self._configured_timezone_name()))

            await self.commit(db)
            return action

    async def list_realtime_object_statistics(self, route_ids: list[str]) -> dict[str, Any]:
        """Return active alert count plus route-based trip and vehicle statistics."""
        unique_route_ids = list(dict.fromkeys(route_ids))
        assignment_type_values = [
            assignment_type.value
            for assignment_type in AssignmentType
            if assignment_type != AssignmentType.MATCH_BY_CACHED_ID
        ]

        def _empty_assignment_types() -> list[dict[str, int]]:
            return [{assignment_type: 0} for assignment_type in assignment_type_values]

        trips_stats = {
            route_id: {
                "num_running_trips": 0,
                "num_realtime_trips": 0,
                "num_monitored_trips": 0,
                "assignment_types": _empty_assignment_types(),
            }
            for route_id in unique_route_ids
        }
        vehicles_stats = {
            route_id: {
                "num_running_trips": 0,
                "num_vehicles": 0,
                "assignment_types": _empty_assignment_types(),
            }
            for route_id in unique_route_ids
        }

        async with self.get_session() as db:
            alerts_count_result = await db.execute(
                select(func.count(ServiceAlert.id)).where(ServiceAlert.is_active.is_(True))
            )
            num_alerts = int(alerts_count_result.scalar_one())

            if unique_route_ids:
                now_value = datetime.now(self._resolve_timezone(self._configured_timezone_name()))

                running_trip_ids_subq = (
                    select(
                        GtfsTrip.route_id.label("route_id"),
                        GtfsTrip.gtfs_id.label("gtfs_trip_id"),
                    )
                    .where(
                        GtfsTrip.route_id.in_(unique_route_ids),
                        GtfsTrip.start_time <= now_value,
                        GtfsTrip.end_time >= now_value,
                    )
                    .distinct()
                    .subquery()
                )

                running_trips_stmt = (
                    select(
                        running_trip_ids_subq.c.route_id,
                        func.count(running_trip_ids_subq.c.gtfs_trip_id),
                    )
                    .group_by(running_trip_ids_subq.c.route_id)
                )
                running_trips_result = await db.execute(running_trips_stmt)
                for route_id, count_value in running_trips_result.all():
                    route_key = str(route_id)
                    count_int = int(count_value or 0)
                    trips_stats[route_key]["num_running_trips"] = count_int
                    vehicles_stats[route_key]["num_running_trips"] = count_int

                per_trip_stop_stats = (
                    select(
                        Trip.id.label("trip_uuid"),
                        running_trip_ids_subq.c.route_id.label("route_id"),
                        func.sum(
                            case(
                                (StopEvent.schedule_relationship != "NO_DATA", 1),
                                else_=0,
                            )
                        ).label("num_non_no_data_events"),
                        func.sum(
                            case(
                                (StopEvent.schedule_relationship.notin_(["NO_DATA", "ADDED"]), 1),
                                else_=0,
                            )
                        ).label("num_realtime_events"),
                    )
                    .join(running_trip_ids_subq, Trip.trip_id == running_trip_ids_subq.c.gtfs_trip_id)
                    .join(StopEvent, StopEvent.trip_id == Trip.trip_id)
                    .where(
                        Trip.is_active.is_(True),
                    )
                    .group_by(Trip.id, running_trip_ids_subq.c.route_id)
                    .subquery()
                )

                realtime_trips_stmt = (
                    select(
                        per_trip_stop_stats.c.route_id,
                        func.sum(
                            case(
                                (per_trip_stop_stats.c.num_non_no_data_events == 0, 1),
                                else_=0,
                            )
                        ).label("num_monitored_trips"),
                        func.sum(
                            case(
                                (per_trip_stop_stats.c.num_realtime_events > 0, 1),
                                else_=0,
                            )
                        ).label("num_realtime_trips"),
                    )
                    .group_by(per_trip_stop_stats.c.route_id)
                )
                realtime_trips_result = await db.execute(realtime_trips_stmt)
                for route_id, monitored_count, realtime_count in realtime_trips_result.all():
                    route_key = str(route_id)
                    trips_stats[route_key]["num_monitored_trips"] = int(monitored_count or 0)
                    trips_stats[route_key]["num_realtime_trips"] = int(realtime_count or 0)

                trip_assignment_type_stmt = (
                    select(
                        running_trip_ids_subq.c.route_id,
                        Trip.assignment_type,
                        func.count(Trip.id).label("num_trips"),
                    )
                    .join(running_trip_ids_subq, Trip.trip_id == running_trip_ids_subq.c.gtfs_trip_id)
                    .where(
                        Trip.is_active.is_(True),
                        Trip.assignment_type.in_(assignment_type_values),
                    )
                    .group_by(running_trip_ids_subq.c.route_id, Trip.assignment_type)
                )
                trip_assignment_type_result = await db.execute(trip_assignment_type_stmt)
                trip_assignment_type_counts: dict[str, dict[str, int]] = {
                    route_id: {assignment_type: 0 for assignment_type in assignment_type_values}
                    for route_id in unique_route_ids
                }
                for route_id, assignment_type, count_value in trip_assignment_type_result.all():
                    trip_assignment_type_counts[str(route_id)][str(assignment_type)] = int(count_value or 0)

                for route_id in unique_route_ids:
                    trips_stats[route_id]["assignment_types"] = [
                        {assignment_type: trip_assignment_type_counts[route_id][assignment_type]}
                        for assignment_type in assignment_type_values
                    ]

                vehicles_stmt = (
                    select(
                        running_trip_ids_subq.c.route_id,
                        func.count(Vehicle.id).label("num_vehicles"),
                    )
                    .join(running_trip_ids_subq, running_trip_ids_subq.c.gtfs_trip_id == Vehicle.trip_id)
                    .join(Trip, Trip.trip_id == Vehicle.trip_id)
                    .where(
                        Trip.is_active.is_(True),
                        Vehicle.is_active.is_(True),
                    )
                    .group_by(running_trip_ids_subq.c.route_id)
                )
                vehicles_result = await db.execute(vehicles_stmt)
                for route_id, count_value in vehicles_result.all():
                    vehicles_stats[str(route_id)]["num_vehicles"] = int(count_value or 0)

                vehicle_assignment_type_stmt = (
                    select(
                        running_trip_ids_subq.c.route_id,
                        Trip.assignment_type,
                        func.count(Vehicle.id).label("num_vehicles"),
                    )
                    .join(running_trip_ids_subq, running_trip_ids_subq.c.gtfs_trip_id == Vehicle.trip_id)
                    .join(Trip, Trip.trip_id == Vehicle.trip_id)
                    .where(
                        Trip.is_active.is_(True),
                        Vehicle.is_active.is_(True),
                        Trip.assignment_type.in_(assignment_type_values),
                    )
                    .group_by(running_trip_ids_subq.c.route_id, Trip.assignment_type)
                )
                vehicle_assignment_type_result = await db.execute(vehicle_assignment_type_stmt)
                vehicle_assignment_type_counts: dict[str, dict[str, int]] = {
                    route_id: {assignment_type: 0 for assignment_type in assignment_type_values}
                    for route_id in unique_route_ids
                }
                for route_id, assignment_type, count_value in vehicle_assignment_type_result.all():
                    vehicle_assignment_type_counts[str(route_id)][str(assignment_type)] = int(count_value or 0)

                for route_id in unique_route_ids:
                    vehicles_stats[route_id]["assignment_types"] = [
                        {assignment_type: vehicle_assignment_type_counts[route_id][assignment_type]}
                        for assignment_type in assignment_type_values
                    ]

            return {
                "num_alerts": num_alerts,
                "trips": trips_stats,
                "vehicles": vehicles_stats,
            }

    @staticmethod
    def _configured_timezone_name() -> str:
        try:
            from echogtfs.common.config import settings

            timezone_name = getattr(settings, "timezone", "UTC")
        except Exception:  # noqa: BLE001
            timezone_name = "UTC"

        if not isinstance(timezone_name, str) or not timezone_name.strip():
            return "UTC"

        return timezone_name

    @staticmethod
    def _resolve_timezone(timezone_name: object) -> ZoneInfo:
        if not isinstance(timezone_name, str) or not timezone_name.strip():
            return ZoneInfo("UTC")

        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")
