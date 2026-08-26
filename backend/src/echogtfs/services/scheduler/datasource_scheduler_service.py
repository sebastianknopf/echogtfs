from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
import json
import logging
import multiprocessing
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from echogtfs.common.config import settings
from echogtfs.services.database.models import AppSetting
from echogtfs.services.scheduler.intf_datasource_scheduler import DatasourceSchedulerInterface

from echogtfs.datasources import get_datasource
from echogtfs.services.caching import CachingService, set_caching_service
from echogtfs.services.database import (
    GtfsRepository,
    RealtimeRepository,
    SystemRepository,
    set_gtfs_repository,
    set_realtime_repository,
    set_system_repository,
)

if TYPE_CHECKING:
    from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
    from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
    from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface

logger = logging.getLogger("uvicorn")


def _run_datasource_process(
    source_id: int,
    database_url: str,
    redis_url: str,
    debug: bool,
) -> dict[str, int]:
    """Run one datasource import in a child process with child-local resources."""
    return asyncio.run(_run_datasource_process_async(source_id, database_url, redis_url, debug))


async def _run_datasource_process_async(
    source_id: int,
    database_url: str,
    redis_url: str,
    debug: bool,
) -> dict[str, int]:
    system_repository = SystemRepository(database_url, debug)
    gtfs_repository = GtfsRepository(database_url, debug)
    realtime_repository = RealtimeRepository(database_url, debug)
    caching_service = CachingService(redis_url)

    try:
        await system_repository.initialize()
        await gtfs_repository.initialize()
        await realtime_repository.initialize()
        await caching_service.initialize()

        set_system_repository(system_repository)
        set_gtfs_repository(gtfs_repository)
        set_realtime_repository(realtime_repository)
        set_caching_service(caching_service)

        source = await system_repository.get_data_source_by_id(source_id)
        if source is None or not source.is_active:
            return {"added": 0, "updated": 0, "deleted": 0}

        datasource = get_datasource(source.type, json.loads(source.config))

        return await datasource.sync_records(
            system_repository,
            realtime_repository,
            gtfs_repository,
            source.id,
            source.name,
            source.log_dumps,
        )
    finally:
        await caching_service.close()
        await gtfs_repository.close()
        await realtime_repository.close()
        await system_repository.close()


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
        system_repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
    ):
        if getattr(self, "_initialized", False):
            return

        self._system_repository = system_repository
        self._realtime_repository = realtime_repository
        self._gtfs_repository = gtfs_repository
        self._scheduler_timezone = self._resolve_scheduler_timezone()
        self._run_state_lock = asyncio.Lock()
        self._running_source_ids: set[int] = set()
        self._process_pool: ProcessPoolExecutor | None = None
        self._closing = False
        self._initialized = True

    @staticmethod
    def _process_pool_size() -> int:
        value = os.getenv("DATASOURCE_PROCESS_POOL_SIZE", "2")
        try:
            return max(1, int(value))
        except ValueError:
            logger.warning("[DatasourceScheduler] Invalid DATASOURCE_PROCESS_POOL_SIZE '%s'; using 2", value)
            return 2

    def _get_process_pool(self) -> ProcessPoolExecutor:
        if self._process_pool is None:
            self._process_pool = ProcessPoolExecutor(
                max_workers=self._process_pool_size(),
                mp_context=multiprocessing.get_context("spawn"),
            )

        return self._process_pool

    async def _run_datasource_in_process(self, source_id: int) -> dict[str, int]:
        loop = asyncio.get_running_loop()

        return await loop.run_in_executor(
            self._get_process_pool(),
            _run_datasource_process,
            source_id,
            settings.database_url,
            settings.redis_url,
            settings.debug,
        )

    async def _try_mark_source_running(self, source_id: int) -> bool:
        async with self._run_state_lock:
            if source_id in self._running_source_ids:
                return False

            self._running_source_ids.add(source_id)
            return True

    async def _mark_source_finished(self, source_id: int) -> None:
        async with self._run_state_lock:
            self._running_source_ids.discard(source_id)

    async def _is_gtfs_import_running(self) -> bool:
        status_value = await self._system_repository.get_app_setting(AppSetting.KEY_GTFS_IMPORT_STATUS)
        return status_value == "running"

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

    async def schedule_all_data_sources(self) -> None:
        """Load active cron-configured data sources and register their jobs."""
        logger.info("[DatasourceScheduler] Loading data sources with cron schedules")

        scheduler = self._get_scheduler()
        for job in scheduler.get_jobs():
            if job.id.startswith("alert_import_"):
                scheduler.remove_job(job.id)

        sources = await self._system_repository.list_active_data_sources_with_cron()
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
        if self._closing:
            return
        
        """Execute one datasource import run if the source exists and is active."""
        if await self._is_gtfs_import_running():
            logger.info(
                "[DatasourceScheduler] Skipping import for data source ID %s: GTFS import is running",
                source_id,
            )

            return

        is_marked = await self._try_mark_source_running(source_id)
        if not is_marked:
            logger.info(
                "[DatasourceScheduler] Skipping import for data source ID %s: source is already running",
                source_id,
            )

            return

        logger.info("[DatasourceScheduler] Starting import for data source ID %s", source_id)

        try:
            source = await self._system_repository.get_data_source_by_id(source_id)
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
                stats = await self._run_datasource_in_process(source.id)

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

                updated = await self._system_repository.update_data_source_last_run_at(source_id, timestamp)
                if not updated:
                    logger.error(
                        "[DatasourceScheduler] Failed to update last_run_at for data source %s",
                        source_id,
                    )
        finally:
            await self._mark_source_finished(source_id)

    async def close(self) -> None:
        if self._closing:
            return

        self._closing = True
        if self._scheduler is not None:
            for job in self._scheduler.get_jobs():
                if job.id.startswith("alert_import_"):
                    self._scheduler.remove_job(job.id)

        if self._process_pool is not None:
            pool = self._process_pool
            self._process_pool = None
            
            await asyncio.to_thread(pool.shutdown, wait=True, cancel_futures=False)
