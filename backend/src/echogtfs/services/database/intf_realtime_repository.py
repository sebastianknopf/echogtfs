from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.services.database.models import ServiceAlert


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
