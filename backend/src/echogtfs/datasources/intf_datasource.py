"""Datasource contract for external service alert imports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from echogtfs.services.database.intf_repository import RepositoryInterface


class DatasourceInterface(ABC):
    """Common contract for all datasource implementations."""

    CONFIG_SCHEMA: list[dict[str, Any]] = []

    @abstractmethod
    def _validate_config(self) -> None:
        """Validate datasource-specific configuration values."""

    @abstractmethod
    async def fetch_alerts(self) -> list[dict[str, Any]]:
        """Fetch and transform external alerts into internal alert dictionaries."""

    @abstractmethod
    async def sync_alerts(
        self,
        repository: RepositoryInterface,
        source_id: int,
        source_name: str,
    ) -> dict[str, int]:
        """Synchronize alerts from datasource into the database."""

    @abstractmethod
    def get_datasource_type(self) -> str:
        """Return the datasource type identifier used in configuration."""

    @classmethod
    @abstractmethod
    def get_config_schema(cls) -> list[dict[str, Any]]:
        """Return a copy of the datasource configuration schema."""
