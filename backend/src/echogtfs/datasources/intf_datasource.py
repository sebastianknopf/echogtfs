"""Datasource contract for external realtime-data imports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface


class DatasourceInterface(ABC):
    """Common contract for all datasource implementations."""

    CONFIG_SCHEMA: list[dict[str, Any]] = []

    @abstractmethod
    def _validate_config(self) -> None:
        """Validate datasource-specific configuration values."""

    @abstractmethod
    async def _fetch_records(self) -> dict[str, Any]:
        """Fetch and transform external realtime payloads into dialect-defined records."""

    @abstractmethod
    async def sync_records(
        self,
        repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
        source_id: int,
        source_name: str,
    ) -> dict[str, int]:
        """Synchronize datasource records into the database."""

    @abstractmethod
    def get_datasource_type(self) -> str:
        """Return the datasource type identifier used in configuration."""

    @classmethod
    @abstractmethod
    def get_config_schema(cls) -> list[dict[str, Any]]:
        """Return a copy of the datasource configuration schema."""
