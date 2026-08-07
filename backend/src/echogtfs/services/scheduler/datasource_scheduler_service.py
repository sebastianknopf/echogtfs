from __future__ import annotations

import asyncio
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
    from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
    from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface

logger = logging.getLogger("uvicorn")


class DatasourceSchedulerService(DatasourceSchedulerInterface):
    """Single-instance service for datasource scheduling and import execution."""

    _instance: DatasourceSchedulerService | None = None
    _scheduler: AsyncIOScheduler | None = None

    def __new__(
        cls,
        repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
    ) -> DatasourceSchedulerService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(
        self,
        repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
    ):
        if getattr(self, "_initialized", False):
            return

        self._repository = repository
        self._realtime_repository = realtime_repository
        self._gtfs_repository = gtfs_repository
        self._scheduler_timezone = self._resolve_scheduler_timezone()
        self._run_state_lock = asyncio.Lock()
        self._running_source_ids: set[int] = set()
        self._initialized = True

    async def _try_mark_source_running(self, source_id: int) -> bool:
        async with self._run_state_lock:
            if source_id in self._running_source_ids:
                return False

            self._running_source_ids.add(source_id)
            return True

    async def _mark_source_finished(self, source_id: int) -> None:
        async with self._run_state_lock:
            self._running_source_ids.discard(source_id)

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

    def _build_cron_trigger(self, cron_expr: str) -> CronTrigger:
        fields = cron_expr.split()
        if len(fields) == 5:
            return CronTrigger.from_crontab(cron_expr, timezone=self._scheduler_timezone)

        if len(fields) == 6:
            second, minute, hour, day, month, day_of_week = fields
            return CronTrigger(
                second=second,
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone=self._scheduler_timezone,
            )

        raise ValueError("Cron expression must have 5 fields (minute-level) or 6 fields (second-level)")

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
                    self._build_cron_trigger(cron_expr),
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
        is_marked = await self._try_mark_source_running(source_id)
        if not is_marked:
            logger.info(
                "[DatasourceScheduler] Skipping import for data source ID %s: source is already running",
                source_id,
            )

            return

        logger.info("[DatasourceScheduler] Starting import for data source ID %s", source_id)

        try:
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
                    self._realtime_repository,
                    self._gtfs_repository,
                    source.id,
                    source.name,
                    source.log_dumps,
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
        finally:
            await self._mark_source_finished(source_id)
