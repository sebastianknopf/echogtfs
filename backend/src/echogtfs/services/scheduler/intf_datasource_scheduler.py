from __future__ import annotations

from abc import ABC, abstractmethod


class DatasourceSchedulerInterface(ABC):
    """Interface for datasource scheduling and import execution."""

    @abstractmethod
    async def schedule_all_data_sources(self) -> None:
        """Load active cron-configured data sources and register their jobs."""
        raise NotImplementedError

    @abstractmethod
    async def schedule_data_source_import(
        self,
        source_id: int,
        source_name: str,
        cron_expr: str | None,
    ) -> None:
        """Create, replace, or remove the scheduled import job for one data source."""
        raise NotImplementedError

    @abstractmethod
    async def run_import_task(self, source_id: int) -> None:
        """Execute one datasource import run."""
        raise NotImplementedError

    @abstractmethod
    async def run_push_task(
        self,
        source_id: int,
        payload: bytes,
        content_type: str | None,
    ) -> dict[str, int]:
        """Execute one datasource push run synchronously and return the sync result counts."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Stop datasource scheduling and drain worker processes."""
        raise NotImplementedError