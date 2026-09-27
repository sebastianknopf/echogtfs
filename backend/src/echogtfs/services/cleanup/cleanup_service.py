"""Cleanup service for expired alerts, outdated trips/vehicles, and old data source logs."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from echogtfs.enum.system import ExpiredRealtimeObjectPolicy
from echogtfs.services.datalog import DatalogService
from echogtfs.services.database import RealtimeRepositoryInterface
from echogtfs.services.database import SystemRepositoryInterface
from echogtfs.services.database.models import AppSetting

logger = logging.getLogger("uvicorn")


class CleanupService:
    """Handles scheduling and execution of cleanup tasks."""

    _scheduler: AsyncIOScheduler | None = None

    def __init__(
        self,
        repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
    ):
        self._repository = repository
        self._realtime_repository = realtime_repository
        self._scheduler_timezone = self._resolve_scheduler_timezone()

    @staticmethod
    def _resolve_scheduler_timezone() -> ZoneInfo:
        timezone_name = os.getenv("TIMEZONE", "UTC").strip() or "UTC"

        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning("[Cleanup] Unknown TIMEZONE '%s'. Falling back to UTC", timezone_name)
            return ZoneInfo("UTC")

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
                    CronTrigger.from_crontab(cron_expr, timezone=self._scheduler_timezone),
                    id=job_id,
                    replace_existing=True,
                )

                logger.info("[Cleanup] Cleanup job scheduled successfully")
            except Exception as exc:  # noqa: BLE001
                logger.error("[Cleanup] Invalid cron expression: %s (%s)", cron_expr, exc)
        else:
            logger.info("[Cleanup] No cron expression set, cleanup job not scheduled")

    async def run_cleanup_task(self) -> None:
        """Execute cleanup of expired internal service alerts, outdated trips/vehicles, and old data source logs."""
        logger.info("[Cleanup] Starting cleanup task")

        try:
            policy_str = await self._repository.get_app_setting(AppSetting.KEY_CLEANUP_EXPIRED_ALERTS_POLICY) or "deactivate"
            policy = ExpiredRealtimeObjectPolicy(policy_str)

            delete_days_value = await self._repository.get_app_setting(AppSetting.KEY_CLEANUP_DELETE_ALERTS_AFTER_DAYS)
            delete_after_days = int(delete_days_value) if delete_days_value is not None else 7

            logger.info("[Cleanup] Policy: %s, Delete after days: %s", policy.value, delete_after_days)

            expired_count = await self._handle_expired_alerts(policy)

            deleted_count = 0
            if delete_after_days >= 0:
                deleted_count = await self._delete_old_expired_alerts(delete_after_days)
            else:
                logger.info("[Cleanup] Delete after days is -1 (never), skipping deletion")

            deleted_trips_count = await self._delete_expired_trips()
            deleted_vehicles_count = await self._delete_expired_vehicles()

            logs_deleted_count = await self._delete_old_logs()

            logger.info(
                "[Cleanup] Task completed. Expired alerts processed: %s, Old alerts deleted: %s, "
                "Trips deleted: %s, Vehicles deleted: %s, Old logs deleted: %s",
                expired_count,
                deleted_count,
                deleted_trips_count,
                deleted_vehicles_count,
                logs_deleted_count,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("[Cleanup] Error during cleanup task: %s", exc, exc_info=True)

    async def _handle_expired_alerts(self, policy: ExpiredRealtimeObjectPolicy) -> int:
        current_timestamp = int(datetime.now(UTC).timestamp())
        alert_ids = await self._realtime_repository.list_expired_alert_ids(
            current_timestamp,
            only_active=policy == ExpiredRealtimeObjectPolicy.DEACTIVATE,
        )

        if not alert_ids:
            logger.info("[Cleanup] No expired alerts found")
            return 0

        count = len(alert_ids)
        if policy == ExpiredRealtimeObjectPolicy.DEACTIVATE:
            await self._realtime_repository.deactivate_service_alerts(alert_ids)
            logger.info("[Cleanup] Deactivated %s expired alerts", count)
        elif policy == ExpiredRealtimeObjectPolicy.DELETE:
            await self._realtime_repository.delete_service_alerts_by_ids(alert_ids)
            logger.info("[Cleanup] Deleted %s expired alerts", count)

        return count

    async def _delete_old_expired_alerts(self, days: int) -> int:
        if days < 0:
            return 0

        cutoff_date = (datetime.now(UTC) - timedelta(days=days)).date()
        cutoff_datetime = datetime.combine(cutoff_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=UTC)
        cutoff_timestamp = int(cutoff_datetime.timestamp())

        alert_ids = await self._realtime_repository.list_alert_ids_expired_before(cutoff_timestamp)
        if not alert_ids:
            logger.info("[Cleanup] No alerts older than %s days found", days)
            return 0

        count = len(alert_ids)
        await self._realtime_repository.delete_service_alerts_by_ids(alert_ids)
        
        logger.info("[Cleanup] Deleted %s alerts (incl. informed entities, translations, active periods) expired for more than %s days", count, days)
        
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

    async def _delete_expired_trips(self) -> int:
        """Purge stop events of trips not updated within the configured max age, deleting the trip itself when no vehicle remains."""
        max_age_value = await self._repository.get_app_setting(AppSetting.KEY_CLEANUP_EXPIRED_TRIPS_MAX_AGE)
        max_age_minutes = int(max_age_value) if max_age_value is not None else 120
        cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)

        trip_ids = await self._realtime_repository.list_trip_ids_updated_before(cutoff)
        if not trip_ids:
            logger.info("[Cleanup] No trips older than %s minutes found", max_age_minutes)
            return 0

        await self._realtime_repository.delete_stop_events_for_trip_ids(trip_ids)

        trip_ids_with_vehicle = await self._realtime_repository.list_trip_ids_with_vehicle(trip_ids)
        trip_ids_to_delete = [trip_id for trip_id in trip_ids if trip_id not in trip_ids_with_vehicle]

        deleted_count = 0
        if trip_ids_to_delete:
            deleted_count = await self._realtime_repository.delete_trips_by_trip_ids(trip_ids_to_delete)

        logger.info(
            "[Cleanup] Purged stop events for %s trips older than %s minutes (%s trips deleted, %s kept alive by an active vehicle)",
            len(trip_ids),
            max_age_minutes,
            deleted_count,
            len(trip_ids) - len(trip_ids_to_delete),
        )

        return deleted_count

    async def _delete_expired_vehicles(self) -> int:
        """Delete vehicle positions not updated within the configured max age, deleting the trip too when no stop events remain."""
        max_age_value = await self._repository.get_app_setting(AppSetting.KEY_CLEANUP_EXPIRED_VEHICLES_MAX_AGE)
        max_age_minutes = int(max_age_value) if max_age_value is not None else 5
        cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)

        vehicles = await self._realtime_repository.list_vehicles_updated_before(cutoff)
        if not vehicles:
            logger.info("[Cleanup] No vehicles older than %s minutes found", max_age_minutes)
            return 0

        vehicle_ids = [vehicle.id for vehicle in vehicles]
        trip_ids = [vehicle.trip_id for vehicle in vehicles if vehicle.trip_id]

        deleted_count = await self._realtime_repository.delete_vehicles_by_ids(vehicle_ids)

        if trip_ids:
            trip_ids_with_stop_events = await self._realtime_repository.list_trip_ids_with_stop_events(trip_ids)
            trip_ids_to_delete = [trip_id for trip_id in trip_ids if trip_id not in trip_ids_with_stop_events]
            if trip_ids_to_delete:
                await self._realtime_repository.delete_trips_by_trip_ids(trip_ids_to_delete)

        logger.info(
            "[Cleanup] Deleted %s vehicles older than %s minutes",
            deleted_count,
            max_age_minutes,
        )

        return deleted_count
