from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.services.database.models import (
    AppSetting,
    DataSource,
    DataSourceEnrichment,
    DataSourceLog,
    DataSourceMapping,
    User,
)


class SystemRepositoryInterface(ABC):
    """Interface for system and nominal-data database access."""

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
    async def get_app_setting(self, key: str) -> str | None:
        """Return app setting value for key or None when setting does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def set_app_setting(self, key: str, value: str) -> None:
        """Create or update one app setting value by key."""
        raise NotImplementedError

    @abstractmethod
    async def get_all_app_settings(self) -> dict[str, str]:
        """Return all app settings as key-value mapping."""
        raise NotImplementedError

    @abstractmethod
    async def list_app_settings(self) -> list[AppSetting]:
        """Return all app setting rows ordered by key."""
        raise NotImplementedError

    @abstractmethod
    async def get_user_by_id(self, user_id: int) -> User | None:
        """Return one user by id, or None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def get_user_by_username(self, username: str) -> User | None:
        """Return one user by username, or None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def user_exists_by_username_or_email(self, username: str, email: str) -> bool:
        """Return True when a user exists with the given username or email."""
        raise NotImplementedError

    @abstractmethod
    async def list_users(self) -> list[User]:
        """Return all users ordered by creation time."""
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    async def delete_user(self, user_id: int) -> bool:
        """Delete one user by id. Returns True when a row was deleted."""
        raise NotImplementedError

    @abstractmethod
    async def list_data_sources(self) -> list[DataSource]:
        """Return all data sources ordered by name with mappings and enrichments loaded."""
        raise NotImplementedError

    @abstractmethod
    async def list_active_data_sources_with_cron(self) -> list[DataSource]:
        """Return active data sources with a cron expression ordered by name."""
        raise NotImplementedError

    @abstractmethod
    async def get_data_source_by_id(self, source_id: int) -> DataSource | None:
        """Return one data source by id with mappings and enrichments, or None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def get_data_source_by_name(self, name: str) -> DataSource | None:
        """Return one data source by name, or None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def data_source_name_exists(self, name: str, *, exclude_id: int | None = None) -> bool:
        """Return True when a data source with the given name exists."""
        raise NotImplementedError

    @abstractmethod
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
        """Create one data source including mappings and enrichments and return it with relationships loaded."""
        raise NotImplementedError

    @abstractmethod
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
        """Update one data source and return it with relationships loaded, or None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def toggle_data_source_active(self, source_id: int) -> DataSource | None:
        """Toggle active state for one data source and return updated model, or None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def update_data_source_last_run_at(self, source_id: int, last_run_at: datetime) -> bool:
        """Persist the last_run_at timestamp for one data source. Returns True when updated."""
        raise NotImplementedError

    @abstractmethod
    async def delete_data_source(self, source_id: int) -> DataSource | None:
        """Delete one data source by id and return deleted model snapshot, or None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def list_data_source_mappings(self, source_id: int, entity_type: str) -> list[DataSourceMapping]:
        """Return all mappings for one data source and entity type ordered by key."""
        raise NotImplementedError

    @abstractmethod
    async def list_data_source_mappings_grouped(self, source_id: int) -> dict[str, dict[str, str]]:
        """Return all data source mappings grouped by entity type."""
        raise NotImplementedError

    @abstractmethod
    async def list_all_data_source_mappings(self) -> list[DataSourceMapping]:
        """Return all data source mappings ordered by id."""
        raise NotImplementedError

    @abstractmethod
    async def replace_data_source_mappings_for_entity_type(
        self,
        source_id: int,
        entity_type: str,
        mappings: list[dict[str, str]],
    ) -> int:
        """Replace mappings for one data source/entity type and return number of inserted rows."""
        raise NotImplementedError

    @abstractmethod
    async def list_data_source_enrichments(self, source_id: int) -> list[dict[str, Any]]:
        """Return enrichment rules for a data source ordered by priority."""
        raise NotImplementedError

    @abstractmethod
    async def list_all_data_source_enrichments(self) -> list[DataSourceEnrichment]:
        """Return all data source enrichments ordered by id."""
        raise NotImplementedError

    @abstractmethod
    async def get_latest_data_source_log(self, source_id: int) -> DataSourceLog | None:
        """Return the most recent log entry for one data source, or None when no logs exist."""
        raise NotImplementedError

    @abstractmethod
    async def list_data_source_logs(self, source_id: int, limit: int) -> list[DataSourceLog]:
        """Return recent log entries for one data source ordered by timestamp descending."""
        raise NotImplementedError

    @abstractmethod
    async def get_data_source_log_by_id(self, log_id: int) -> DataSourceLog | None:
        """Return one data source log entry by id, or None when not found."""
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    async def list_data_source_log_uuids_for_data_source(self, data_source_id: int) -> list[uuid.UUID]:
        """Return all log file UUIDs for one data source."""
        raise NotImplementedError

    @abstractmethod
    async def delete_data_source_logs_for_data_source(self, data_source_id: int) -> int:
        """Delete all data source log rows for one data source and return affected row count."""
        raise NotImplementedError

    @abstractmethod
    async def list_data_source_log_uuids_before(self, cutoff_time: datetime) -> list[uuid.UUID]:
        """Return UUIDs of data source log files older than cutoff time."""
        raise NotImplementedError

    @abstractmethod
    async def delete_data_source_logs_before(self, cutoff_time: datetime) -> int:
        """Delete data source log rows older than cutoff time and return affected row count."""
        raise NotImplementedError

    @abstractmethod
    async def get_data_source_invalid_reference_policy(self, source_id: int) -> str:
        """Return invalid reference policy configured for a data source."""
        raise NotImplementedError
