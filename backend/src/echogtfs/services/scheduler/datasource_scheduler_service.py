from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from echogtfs.services.scheduler.intf_datasource_scheduler import DatasourceSchedulerInterface

if TYPE_CHECKING:
    from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
    from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface

logger = logging.getLogger("uvicorn")


class DatasourceSchedulerService(DatasourceSchedulerInterface):
    """Single-instance service for datasource scheduling and import execution."""

    _instance: DatasourceSchedulerService | None = None
    _scheduler: AsyncIOScheduler | None = None

    def __new__(
        cls,
        repository: SystemRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
    ) -> DatasourceSchedulerService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(
        self,
        repository: SystemRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
    ):
        self._repository = repository
        self._gtfs_repository = gtfs_repository
        self._scheduler_timezone = self._resolve_scheduler_timezone()

    @staticmethod
    def _resolve_scheduler_timezone() -> ZoneInfo:
        timezone_name = os.getenv("TIMEZONE", "UTC").strip() or "UTC"

        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning(
                "[DatasourceScheduler] Unknown TIMEZONE '%s'. Falling back to UTC",
                timezone_name,
            )
            return ZoneInfo("UTC")

    @classmethod
    def _get_scheduler(cls) -> AsyncIOScheduler:
        if cls._scheduler is None:
            cls._scheduler = AsyncIOScheduler()
            cls._scheduler.start()

        return cls._scheduler

    @staticmethod
    def _get_datasource(source_type: str, config: dict[str, object]):
        from echogtfs.datasources import get_datasource

        return get_datasource(source_type, config)

    async def schedule_all_data_sources(self) -> None:
        """Load active cron-configured data sources and register their jobs."""
        logger.info("[DatasourceScheduler] Loading data sources with cron schedules")

        scheduler = self._get_scheduler()
        for job in scheduler.get_jobs():
            if job.id.startswith("alert_import_"):
                scheduler.remove_job(job.id)

        sources = await self._repository.list_active_data_sources_with_cron()
        for source in sources:
            if source.cron:
                await self.schedule_data_source_import(source.id, source.name, source.cron)

        logger.info(
            "[DatasourceScheduler] Scheduled %s active data source import jobs",
            len(sources),
        )

    async def schedule_data_source_import(
        self,
        source_id: int,
        source_name: str,
        cron_expr: str | None,
    ) -> None:
        """Create, replace, or remove the scheduled import job for one data source."""
        scheduler = self._get_scheduler()
        job_id = f"alert_import_{source_id}"

        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(
                "[DatasourceScheduler] Removed job for source %s (ID: %s)",
                source_name,
                source_id,
            )

        if cron_expr:
            try:
                scheduler.add_job(
                    self.run_import_task,
                    CronTrigger.from_crontab(cron_expr, timezone=self._scheduler_timezone),
                    args=[source_id],
                    id=job_id,
                    replace_existing=True,
                )
                
                logger.info(
                    "[DatasourceScheduler] Scheduled job for source %s (ID: %s): %s",
                    source_name,
                    source_id,
                    cron_expr,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "[DatasourceScheduler] Invalid cron expression for source %s: %s (%s)",
                    source_name,
                    cron_expr,
                    exc,
                )

    async def run_import_task(self, source_id: int) -> None:
        """Execute one datasource import run if the source exists and is active."""
        logger.info("[DatasourceScheduler] Starting import for data source ID %s", source_id)

        source = await self._repository.get_data_source_by_id(source_id)
        if source is None:
            logger.error("[DatasourceScheduler] Data source %s not found", source_id)
            return

        if not source.is_active:
            logger.info(
                "[DatasourceScheduler] Data source '%s' is inactive, skipping import",
                source.name,
            )
            return

        try:
            config = json.loads(source.config)
            datasource = self._get_datasource(source.type, config)

            stats = await datasource.sync_records(
                self._repository,
                self._gtfs_repository,
                source.id,
                source.name,
            )

            logger.info(
                "[DatasourceScheduler] Import task completed for '%s': created=%s, updated=%s, deleted=%s",
                source.name,
                stats["added"],
                stats["updated"],
                stats["deleted"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[DatasourceScheduler] Import task failed for '%s': %s",
                source.name,
                exc,
                exc_info=True,
            )

        finally:
            timestamp = datetime.now(UTC)

            updated = await self._repository.update_data_source_last_run_at(source_id, timestamp)
            if not updated:
                logger.error(
                    "[DatasourceScheduler] Failed to update last_run_at for data source %s",
                    source_id,
                )
