"""Service alert cleanup service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from echogtfs.enum.system import ExpiredAlertPolicy
from echogtfs.services.datalog import DatalogService
from echogtfs.services.database import SystemRepositoryInterface
from echogtfs.services.database.models import AppSetting

logger = logging.getLogger("uvicorn")


class CleanupService:
    """Handles scheduling and execution of cleanup tasks."""

    _scheduler: AsyncIOScheduler | None = None

    def __init__(self, repository: SystemRepositoryInterface):
        self._repository = repository

    @classmethod
    def _get_scheduler(cls) -> AsyncIOScheduler:
        if cls._scheduler is None:
            cls._scheduler = AsyncIOScheduler()
            cls._scheduler.start()
        
        return cls._scheduler

    async def schedule_from_settings(self) -> None:
        """Read cleanup cron setting and (re)schedule cleanup job."""
        cron_expr = await self._repository.get_app_setting(AppSetting.KEY_CLEANUP_CRON) or "*/10 * * * *"

        scheduler = self._get_scheduler()
        job_id = "alert_cleanup_cron"

        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info("[Cleanup] Removed existing cleanup job")

        if cron_expr:
            try:
                logger.info("[Cleanup] Scheduling cleanup job with cron: %s", cron_expr)
                
                scheduler.add_job(
                    self.run_cleanup_task,
                    CronTrigger.from_crontab(cron_expr),
                    id=job_id,
                    replace_existing=True,
                )

                logger.info("[Cleanup] Cleanup job scheduled successfully")
            except Exception as exc:  # noqa: BLE001
                logger.error("[Cleanup] Invalid cron expression: %s (%s)", cron_expr, exc)
        else:
            logger.info("[Cleanup] No cron expression set, cleanup job not scheduled")

    async def run_cleanup_task(self) -> None:
        """Execute cleanup of expired internal service alerts and old data source logs."""
        logger.info("[Cleanup] Starting cleanup task")

        try:
            policy_str = await self._repository.get_app_setting(AppSetting.KEY_CLEANUP_EXPIRED_POLICY) or "deactivate"
            policy = ExpiredAlertPolicy(policy_str)

            delete_days_value = await self._repository.get_app_setting(AppSetting.KEY_CLEANUP_DELETE_AFTER_DAYS)
            delete_after_days = int(delete_days_value) if delete_days_value is not None else -1

            logger.info("[Cleanup] Policy: %s, Delete after days: %s", policy.value, delete_after_days)

            expired_count = await self._handle_expired_alerts(policy)

            deleted_count = 0
            if delete_after_days >= 0:
                deleted_count = await self._delete_old_expired_alerts(delete_after_days)
            else:
                logger.info("[Cleanup] Delete after days is -1 (never), skipping deletion")

            logs_deleted_count = await self._delete_old_logs()

            logger.info(
                "[Cleanup] Task completed. Expired alerts processed: %s, Old alerts deleted: %s, Old logs deleted: %s",
                expired_count,
                deleted_count,
                logs_deleted_count,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[Cleanup] Error during cleanup task: %s", exc, exc_info=True)

    async def _handle_expired_alerts(self, policy: ExpiredAlertPolicy) -> int:
        current_timestamp = int(datetime.now(UTC).timestamp())
        alert_ids = await self._repository.list_expired_internal_alert_ids(
            current_timestamp,
            only_active=policy == ExpiredAlertPolicy.DEACTIVATE,
        )

        if not alert_ids:
            logger.info("[Cleanup] No expired internal alerts found")
            return 0

        count = len(alert_ids)
        if policy == ExpiredAlertPolicy.DEACTIVATE:
            await self._repository.deactivate_service_alerts(alert_ids)
            logger.info("[Cleanup] Deactivated %s expired internal alerts", count)
        elif policy == ExpiredAlertPolicy.DELETE:
            await self._repository.delete_service_alerts_by_ids(alert_ids)
            logger.info("[Cleanup] Deleted %s expired internal alerts", count)

        return count

    async def _delete_old_expired_alerts(self, days: int) -> int:
        if days < 0:
            return 0

        cutoff_date = (datetime.now(UTC) - timedelta(days=days)).date()
        cutoff_datetime = datetime.combine(cutoff_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=UTC)
        cutoff_timestamp = int(cutoff_datetime.timestamp())

        alert_ids = await self._repository.list_internal_alert_ids_expired_before(cutoff_timestamp)
        if not alert_ids:
            logger.info("[Cleanup] No internal alerts older than %s days found", days)
            return 0

        count = len(alert_ids)
        await self._repository.delete_service_alerts_by_ids(alert_ids)
        
        logger.info("[Cleanup] Deleted %s internal alerts expired for more than %s days", count, days)
        
        return count

    async def _delete_old_logs(self) -> int:
        cutoff_time = datetime.now(UTC) - timedelta(hours=24)

        log_uuids = await self._repository.list_data_source_log_uuids_before(cutoff_time)
        if not log_uuids:
            logger.info("[Cleanup] No data source logs older than 24 hours found")
            return 0

        count = len(log_uuids)
        deleted_files = await DatalogService(self._repository).delete_log_files_by_uuids(log_uuids)
        await self._repository.delete_data_source_logs_before(cutoff_time)

        logger.info(
            "[Cleanup] Deleted %s data source logs older than 24 hours (%s files deleted from disk)",
            count,
            deleted_files,
        )

        return count
