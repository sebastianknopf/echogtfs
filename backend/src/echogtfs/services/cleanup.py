"""Service alert cleanup service.

Manages cleanup of expired internal service alerts based on configured policy.
Runs on a scheduled cron job to:
- Deactivate or delete internal alerts whose last active period has expired
- Delete old expired alerts after a configured retention period

External alerts (with data_source_id) are never cleaned up automatically,
as they are always synchronized from their data sources.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.database import AsyncSessionLocal
from echogtfs.models import AppSetting, ExpiredAlertPolicy, ServiceAlert, ServiceAlertActivePeriod

logger = logging.getLogger("uvicorn")

_scheduler = None

# AppSetting keys
KEY_CLEANUP_CRON = "cleanup_cron"
KEY_CLEANUP_POLICY = "cleanup_expired_policy"
KEY_CLEANUP_DELETE_DAYS = "cleanup_delete_after_days"


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.start()
    return _scheduler


async def schedule_cleanup_from_settings(db: AsyncSession | None = None) -> None:
    """
    Read cleanup settings from AppSettings and (re)schedule cleanup job.
    Called at application startup and when settings are updated.
    """
    close_db = False
    if db is None:
        db = await AsyncSessionLocal().__aenter__()
        close_db = True
    
    # Load settings
    cron_row = await db.get(AppSetting, KEY_CLEANUP_CRON)
    cron_expr = cron_row.value if cron_row else "*/10 * * * *"  # Default: every 10 minutes
    
    scheduler = get_scheduler()
    job_id = "alert_cleanup_cron"
    
    # Remove existing job
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("[Cleanup] Removed existing cleanup job")
    
    # Add new job with cron expression
    if cron_expr:
        try:
            logger.info(f"[Cleanup] Scheduling cleanup job with cron: {cron_expr}")
            scheduler.add_job(
                run_cleanup_task,
                CronTrigger.from_crontab(cron_expr),
                id=job_id,
                replace_existing=True,
            )
            logger.info("[Cleanup] Cleanup job scheduled successfully")
        except Exception as e:
            logger.error(f"[Cleanup] Invalid cron expression: {cron_expr} ({e})")
    else:
        logger.info("[Cleanup] No cron expression set, cleanup job not scheduled")
    
    if close_db:
        await db.__aexit__(None, None, None)


async def run_cleanup_task() -> None:
    """
    Execute cleanup of expired internal service alerts.
    Called by the scheduler.
    """
    logger.info("[Cleanup] Starting cleanup task")
    
    async with AsyncSessionLocal() as db:
        try:
            # Load settings
            policy_row = await db.get(AppSetting, KEY_CLEANUP_POLICY)
            policy_str = policy_row.value if policy_row else "deactivate"
            policy = ExpiredAlertPolicy(policy_str)
            
            delete_days_row = await db.get(AppSetting, KEY_CLEANUP_DELETE_DAYS)
            delete_after_days = int(delete_days_row.value) if delete_days_row else -1
            
            logger.info(f"[Cleanup] Policy: {policy.value}, Delete after days: {delete_after_days}")
            
            # Step 1: Handle expired alerts according to policy
            expired_count = await _handle_expired_alerts(db, policy)
            
            # Step 2: Delete old expired alerts (if configured)
            deleted_count = 0
            if delete_after_days >= 0:
                deleted_count = await _delete_old_expired_alerts(db, delete_after_days)
            else:
                logger.info("[Cleanup] Delete after days is -1 (never), skipping deletion")
            
            await db.commit()
            
            logger.info(
                f"[Cleanup] Task completed. "
                f"Expired alerts processed: {expired_count}, "
                f"Old alerts deleted: {deleted_count}"
            )
            
        except Exception as e:
            logger.error(f"[Cleanup] Error during cleanup task: {e}", exc_info=True)
            await db.rollback()


async def _handle_expired_alerts(db: AsyncSession, policy: ExpiredAlertPolicy) -> int:
    """
    Handle expired internal alerts according to policy.
    
    Returns:
        Number of alerts processed
    """
    current_timestamp = int(datetime.now(UTC).timestamp())
    
    # Find internal alerts (data_source_id IS NULL) with expired active periods
    # An alert is expired if:
    # - It has at least one active_period
    # - ALL active_periods have end_time set
    # - The maximum end_time is less than current timestamp
    
    # Subquery to find alerts where all periods have ended
    subquery = (
        select(ServiceAlertActivePeriod.alert_id)
        .group_by(ServiceAlertActivePeriod.alert_id)
        .having(
            func.max(ServiceAlertActivePeriod.end_time).isnot(None) &
            (func.max(ServiceAlertActivePeriod.end_time) < current_timestamp)
        )
    )
    
    # Find internal alerts that are in the subquery
    query = select(ServiceAlert.id).where(
        ServiceAlert.data_source_id.is_(None),
        ServiceAlert.id.in_(subquery)
    )
    
    if policy == ExpiredAlertPolicy.DEACTIVATE:
        # Only process active alerts
        query = query.where(ServiceAlert.is_active == True)
    
    result = await db.execute(query)
    alert_ids = [row[0] for row in result.all()]
    
    if not alert_ids:
        logger.info("[Cleanup] No expired internal alerts found")
        return 0
    
    count = len(alert_ids)
    
    if policy == ExpiredAlertPolicy.DEACTIVATE:
        # Deactivate expired alerts
        await db.execute(
            update(ServiceAlert)
            .where(ServiceAlert.id.in_(alert_ids))
            .values(is_active=False)
        )
        logger.info(f"[Cleanup] Deactivated {count} expired internal alerts")
    
    elif policy == ExpiredAlertPolicy.DELETE:
        # Delete expired alerts (cascade will delete related records)
        await db.execute(
            delete(ServiceAlert)
            .where(ServiceAlert.id.in_(alert_ids))
        )
        logger.info(f"[Cleanup] Deleted {count} expired internal alerts")
    
    return count


async def _delete_old_expired_alerts(db: AsyncSession, days: int) -> int:
    """
    Delete internal alerts that expired more than 'days' ago.
    
    Only the calendar date is considered, not the time. If an alert expires
    on day X at any time, it will be deleted on day X+days at the first run.
    
    Args:
        days: Number of days after expiration to delete alerts
    
    Returns:
        Number of alerts deleted
    """
    if days < 0:
        return 0
    
    # Calculate cutoff date: today minus 'days' days
    cutoff_date = (datetime.now(UTC) - timedelta(days=days)).date()
    # Set to midnight of the NEXT day (= end of cutoff_date)
    # This means all alerts that expired on cutoff_date or earlier will be deleted
    cutoff_datetime = datetime.combine(cutoff_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=UTC)
    cutoff_timestamp = int(cutoff_datetime.timestamp())
    
    # Find internal alerts where the maximum end_time is older than cutoff
    subquery = (
        select(ServiceAlertActivePeriod.alert_id)
        .group_by(ServiceAlertActivePeriod.alert_id)
        .having(
            func.max(ServiceAlertActivePeriod.end_time).isnot(None) &
            (func.max(ServiceAlertActivePeriod.end_time) < cutoff_timestamp)
        )
    )
    
    # Find internal alerts that are in the subquery
    query = select(ServiceAlert.id).where(
        ServiceAlert.data_source_id.is_(None),
        ServiceAlert.id.in_(subquery)
    )
    
    result = await db.execute(query)
    alert_ids = [row[0] for row in result.all()]
    
    if not alert_ids:
        logger.info(f"[Cleanup] No internal alerts older than {days} days found")
        return 0
    
    count = len(alert_ids)
    
    # Delete old expired alerts
    await db.execute(
        delete(ServiceAlert)
        .where(ServiceAlert.id.in_(alert_ids))
    )
    
    logger.info(f"[Cleanup] Deleted {count} internal alerts expired for more than {days} days")
    
    return count
