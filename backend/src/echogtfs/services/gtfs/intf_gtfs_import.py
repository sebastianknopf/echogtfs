from __future__ import annotations

from abc import ABC, abstractmethod


class GtfsImportInterface(ABC):
    """Interface for GTFS static import services."""

    @abstractmethod
    async def get_status(self) -> dict[str, str | None]:
        """Return feed url, cron, status, imported_at, and message."""
        raise NotImplementedError

    @abstractmethod
    async def is_import_running(self) -> bool:
        """Return True when an import is currently running."""
        raise NotImplementedError

    @abstractmethod
    async def update_configuration(self, *, feed_url: str | None, cron: str | None) -> dict[str, str]:
        """Update feed URL and/or cron expression and return updated payload."""
        raise NotImplementedError

    @abstractmethod
    async def schedule_import_from_cron(self) -> None:
        """Read cron setting and (re)schedule the periodic GTFS import job."""
        raise NotImplementedError

    @abstractmethod
    async def run_import_task(self) -> None:
        """Execute one GTFS import run and persist status updates."""
        raise NotImplementedError
