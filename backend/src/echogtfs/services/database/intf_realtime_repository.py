from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.services.database.models import ServiceAlert, Trip, Vehicle


class RealtimeRepositoryInterface(ABC):
    """Interface for realtime-table data access."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize repository resources and validate connectivity."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close repository resources."""
        raise NotImplementedError

    @abstractmethod
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a managed database session owned by the repository."""
        raise NotImplementedError

    @abstractmethod
    async def delete_alerts_for_data_source(self, source_id: int) -> int:
        """Delete all alerts for one data source and return deleted row count."""
        raise NotImplementedError

    @abstractmethod
    async def update_service_alert_source_name(self, old_name: str, new_name: str) -> None:
        """Rename service alert source text from old_name to new_name."""
        raise NotImplementedError

    @abstractmethod
    async def get_realtime_service_alerts(self) -> list[ServiceAlert]:
        """Return active realtime service alerts with all required relationships."""
        raise NotImplementedError

    @abstractmethod
    async def list_expired_internal_alert_ids(self, current_timestamp: int, *, only_active: bool) -> list[uuid.UUID]:
        """Return internal alert ids where all active periods ended before current timestamp."""
        raise NotImplementedError

    @abstractmethod
    async def list_internal_alert_ids_expired_before(self, cutoff_timestamp: int) -> list[uuid.UUID]:
        """Return internal alert ids where all active periods ended before cutoff timestamp."""
        raise NotImplementedError

    @abstractmethod
    async def deactivate_service_alerts(self, alert_ids: list[uuid.UUID]) -> int:
        """Set is_active=False for the provided alert ids and return affected row count."""
        raise NotImplementedError

    @abstractmethod
    async def delete_service_alerts_by_ids(self, alert_ids: list[uuid.UUID]) -> int:
        """Delete service alerts by ids and return affected row count."""
        raise NotImplementedError

    @abstractmethod
    async def list_service_alerts_for_data_source(self, source_id: int) -> list[ServiceAlert]:
        """Return all service alerts currently linked to one data source."""
        raise NotImplementedError

    @abstractmethod
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
        """Return paginated service alerts with total count and required relationships loaded."""
        raise NotImplementedError

    @abstractmethod
    async def get_service_alert_by_id_with_relations(self, alert_id: uuid.UUID) -> ServiceAlert | None:
        """Return one service alert by id with all required relationships, or None when not found."""
        raise NotImplementedError

    @abstractmethod
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
        """Create one service alert including child records and return it with relationships loaded."""
        raise NotImplementedError

    @abstractmethod
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
        """Update one service alert and optionally replace child records. Returns None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def toggle_service_alert_active(self, alert_id: uuid.UUID) -> ServiceAlert | None:
        """Toggle the is_active flag for one service alert and return updated model, or None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def list_service_alerts_by_ids(self, alert_ids: list[uuid.UUID]) -> list[ServiceAlert]:
        """Return service alerts by ids."""
        raise NotImplementedError

    @abstractmethod
    async def delete_service_alerts_for_data_source_by_ids(
        self,
        source_id: int,
        alert_ids: list[uuid.UUID],
    ) -> int:
        """Delete service alerts by ids only when they belong to a specific data source."""
        raise NotImplementedError

    @abstractmethod
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
        """Create or update one synchronized alert and replace child records."""
        raise NotImplementedError

    @abstractmethod
    async def get_realtime_trips(self) -> list[Trip]:
        """Return active realtime trips with stop events and vehicle relations loaded."""
        raise NotImplementedError

    @abstractmethod
    async def list_trips_paginated(
        self,
        *,
        page: int,
        limit: int,
        sort: str,
        search: str,
        is_active: bool | None,
    ) -> tuple[list[Trip], int]:
        """Return paginated realtime trips with total count and required relationships loaded."""
        raise NotImplementedError

    @abstractmethod
    async def list_trip_ids_with_invalid_stop_events(self, trip_ids: list[str]) -> set[str]:
        """Return trip ids where at least one stop event has is_valid=False."""
        raise NotImplementedError

    @abstractmethod
    async def toggle_trip_active(self, trip_uuid: uuid.UUID) -> Trip | None:
        """Toggle the is_active flag for one realtime trip and return updated model."""
        raise NotImplementedError

    @abstractmethod
    async def delete_trips_for_data_source(self, source_id: int) -> int:
        """Delete all realtime trips for one data source and return deleted row count."""
        raise NotImplementedError

    @abstractmethod
    async def list_trips_for_data_source(self, source_id: int) -> list[Trip]:
        """Return all realtime trips currently linked to one data source."""
        raise NotImplementedError

    @abstractmethod
    async def list_trips_by_ids(self, trip_ids: list[uuid.UUID]) -> list[Trip]:
        """Return realtime trips by ids."""
        raise NotImplementedError

    @abstractmethod
    async def list_trips_by_trip_ids(self, trip_ids: list[str]) -> list[Trip]:
        """Return realtime trips by trip_id values."""
        raise NotImplementedError

    @abstractmethod
    async def list_trip_ids_with_stop_events(self, trip_ids: list[str]) -> set[str]:
        """Return trip_id values that currently have at least one realtime stop event."""
        raise NotImplementedError

    @abstractmethod
    async def delete_trips_by_trip_ids(self, trip_ids: list[str]) -> int:
        """Delete realtime trip rows by trip_id and return the deleted row count."""
        raise NotImplementedError

    @abstractmethod
    async def delete_trips_for_data_source_by_ids(
        self,
        source_id: int,
        trip_ids: list[uuid.UUID],
    ) -> int:
        """Delete realtime trips by ids only when they belong to a specific data source."""
        raise NotImplementedError

    @abstractmethod
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
        """Create or update one synchronized trip update and replace stop event records."""
        raise NotImplementedError

    @abstractmethod
    async def get_realtime_vehicles(self) -> list[Vehicle]:
        """Return active realtime vehicle positions with trip relations loaded."""
        raise NotImplementedError

    @abstractmethod
    async def list_vehicles_paginated(
        self,
        *,
        page: int,
        limit: int,
        search: str,
        is_active: bool | None,
    ) -> tuple[list[Vehicle], int]:
        """Return paginated realtime vehicles with total count and required relationships loaded."""
        raise NotImplementedError    

    @abstractmethod
    async def toggle_vehicle_active(self, vehicle_uuid: uuid.UUID) -> Vehicle | None:
        """Toggle the is_active flag for one realtime vehicle and return updated model."""
        raise NotImplementedError

    @abstractmethod
    async def delete_vehicles_for_data_source(self, source_id: int) -> int:
        """Delete all realtime vehicles for one data source and return deleted row count."""
        raise NotImplementedError

    @abstractmethod
    async def list_vehicles_for_data_source(self, source_id: int) -> list[Vehicle]:
        """Return all realtime vehicles currently linked to one data source."""
        raise NotImplementedError

    @abstractmethod
    async def list_vehicles_by_ids(self, vehicle_ids: list[uuid.UUID]) -> list[Vehicle]:
        """Return realtime vehicles by ids."""
        raise NotImplementedError

    @abstractmethod
    async def delete_vehicles_for_data_source_by_ids(
        self,
        source_id: int,
        vehicle_ids: list[uuid.UUID],
    ) -> int:
        """Delete realtime vehicles by ids only when they belong to a specific data source."""
        raise NotImplementedError

    @abstractmethod
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
        """Create or update one synchronized vehicle position and ensure linked trip exists."""
        raise NotImplementedError
