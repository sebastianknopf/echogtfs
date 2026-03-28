"""Service alert import service from external data sources.

Manages scheduled imports from configured data sources using their adapters.
Each data source runs on its own cron schedule and updates service alerts.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.database import AsyncSessionLocal
from echogtfs.models import DataSource
from echogtfs.services.adapters import get_adapter

logger = logging.getLogger("uvicorn")

_scheduler = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.start()
    return _scheduler


async def schedule_all_data_sources() -> None:
    """
    Load all data sources with cron expressions and register their jobs.
    Called at application startup.
    """
    logger.info("[AlertImport] Loading data sources with cron schedules")
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DataSource).where(DataSource.cron.isnot(None))
        )
        sources = result.scalars().all()
        
        scheduler = get_scheduler()
        # Clear all existing alert import jobs
        for job in scheduler.get_jobs():
            if job.id.startswith("alert_import_"):
                scheduler.remove_job(job.id)
        
        # Register new jobs
        for source in sources:
            if source.cron:
                await schedule_data_source_import(source.id, source.name, source.cron)
        
        logger.info(f"[AlertImport] Scheduled {len(sources)} data source import jobs")


async def schedule_data_source_import(source_id: int, source_name: str, cron_expr: str | None) -> None:
    """
    Schedule or remove a cron job for a specific data source.
    
    Args:
        source_id: Database ID of the data source
        source_name: Name of the data source (for logging)
        cron_expr: Cron expression or None to remove the job
    """
    scheduler = get_scheduler()
    job_id = f"alert_import_{source_id}"
    
    # Remove existing job if any
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"[AlertImport] Removed job for source {source_name} (ID: {source_id})")
    
    # Add new job if cron expression is provided
    if cron_expr:
        try:
            scheduler.add_job(
                run_import_task,
                CronTrigger.from_crontab(cron_expr),
                args=[source_id],
                id=job_id,
                replace_existing=True,
            )
            logger.info(f"[AlertImport] Scheduled job for source {source_name} (ID: {source_id}): {cron_expr}")
        except Exception as e:
            logger.error(f"[AlertImport] Invalid cron expression for source {source_name}: {cron_expr} ({e})")


async def run_import_task(source_id: int) -> None:
    """
    Import service alerts from a specific data source.
    Called by the scheduler or manually triggered.
    
    Args:
        source_id: Database ID of the data source to import from
    """
    logger.info(f"[AlertImport] Starting import for data source ID {source_id}")
    
    async with AsyncSessionLocal() as db:
        # Load data source
        result = await db.execute(
            select(DataSource).where(DataSource.id == source_id)
        )
        source = result.scalar_one_or_none()
        
        if not source:
            logger.error(f"[AlertImport] Data source {source_id} not found")
            return
        
        try:
            # Create adapter and fetch alerts
            import json
            config = json.loads(source.config)
            
            # Add source name to config for deterministic ID generation
            config["_source_name"] = source.name
            
            adapter = get_adapter(source.type, config)
            
            # Delegate all sync logic to the adapter
            stats = await adapter.sync_alerts(db, source.id, source.name)
            
            # Update last_run_at timestamp
            # Refresh source to ensure it's still attached to the session
            await db.refresh(source)
            source.last_run_at = datetime.now(UTC)
            
            await db.commit()
            
            logger.info(
                f"[AlertImport] Import completed for {source.name}: "
                f"+{stats['added']} ~{stats['updated']} -{stats['deleted']}"
            )
            
        except Exception as e:
            logger.error(f"[AlertImport] Failed to import from {source.name}: {e}", exc_info=True)
            await db.rollback()
