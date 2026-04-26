"""Data source logging service.

Manages logging of HTTP requests to external data sources.
Stores metadata in the database and response dumps as files.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.database import AsyncSessionLocal
from echogtfs.models import DataSourceLog

logger = logging.getLogger("uvicorn")

# Default log directory - can be overridden by environment variable
DEFAULT_LOG_DIR = Path("/var/log/echogtfs/datasources")


def get_log_directory() -> Path:
    """Get the directory for storing log files."""
    import os
    log_dir_str = os.getenv("DATASOURCE_LOG_DIR", str(DEFAULT_LOG_DIR))
    log_dir = Path(log_dir_str)
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


async def create_log_entry(
    data_source_id: int,
    request_url: str,
    response_content: bytes | str,
    request_headers: dict[str, Any] | None = None,
    response_headers: dict[str, Any] | None = None,
    response_mimetype: str | None = None,
    status_code: int | None = None,
    db: AsyncSession | None = None,
) -> DataSourceLog:
    """
    Create a new log entry for a data source request.
    
    Args:
        data_source_id: ID of the data source
        request_url: URL that was requested
        response_content: Response body content (bytes or string)
        request_headers: Request headers dictionary
        response_headers: Response headers dictionary
        response_mimetype: MIME type of the response (e.g., 'application/json')
        status_code: HTTP status code
        db: Database session (creates new if not provided)
    
    Returns:
        Created DataSourceLog instance
    """
    close_db = False
    if db is None:
        db = await AsyncSessionLocal().__aenter__()
        close_db = True
    
    try:
        # Generate UUID for log file
        log_uuid = uuid.uuid4()
        
        # Convert content to bytes if string
        if isinstance(response_content, str):
            content_bytes = response_content.encode("utf-8")
        else:
            content_bytes = response_content
        
        # Save log file
        log_dir = get_log_directory()
        log_file_path = log_dir / str(log_uuid)
        
        try:
            log_file_path.write_bytes(content_bytes)
            logger.info(f"[DataLog] Saved log file: {log_file_path}")
        except Exception as e:
            logger.error(f"[DataLog] Failed to save log file {log_file_path}: {e}")
            raise
        
        # Convert headers to JSON strings
        request_headers_json = json.dumps(request_headers) if request_headers else None
        response_headers_json = json.dumps(response_headers) if response_headers else None
        
        # Create database entry
        log_entry = DataSourceLog(
            data_source_id=data_source_id,
            timestamp=datetime.now(UTC),
            request_url=request_url,
            request_headers=request_headers_json,
            response_headers=response_headers_json,
            response_mimetype=response_mimetype,
            status_code=status_code,
            response_size=len(content_bytes),
            log_file_uuid=log_uuid,
        )
        
        db.add(log_entry)
        await db.commit()
        await db.refresh(log_entry)
        
        logger.info(
            f"[DataLog] Created log entry {log_entry.id} for data source "
            f"{data_source_id} (file: {log_uuid})"
        )
        
        return log_entry
        
    finally:
        if close_db:
            await db.__aexit__(None, None, None)


async def get_logs_for_data_source(
    data_source_id: int,
    limit: int = 100,
    db: AsyncSession | None = None,
) -> list[DataSourceLog]:
    """
    Get recent log entries for a data source.
    
    Args:
        data_source_id: ID of the data source
        limit: Maximum number of entries to return (default 100)
        db: Database session (creates new if not provided)
    
    Returns:
        List of DataSourceLog instances, ordered by timestamp descending
    """
    close_db = False
    if db is None:
        db = await AsyncSessionLocal().__aenter__()
        close_db = True
    
    try:
        stmt = (
            select(DataSourceLog)
            .where(DataSourceLog.data_source_id == data_source_id)
            .order_by(DataSourceLog.timestamp.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        logs = list(result.scalars().all())
        
        logger.debug(f"[DataLog] Retrieved {len(logs)} log entries for data source {data_source_id}")
        
        return logs
        
    finally:
        if close_db:
            await db.__aexit__(None, None, None)


async def get_log_content(log_uuid: uuid.UUID) -> bytes | None:
    """
    Retrieve the content of a log file.
    
    Args:
        log_uuid: UUID of the log file
    
    Returns:
        Log file content as bytes, or None if file not found
    """
    log_dir = get_log_directory()
    log_file_path = log_dir / str(log_uuid)
    
    try:
        if log_file_path.exists():
            return log_file_path.read_bytes()
        else:
            logger.warning(f"[DataLog] Log file not found: {log_file_path}")
            return None
    except Exception as e:
        logger.error(f"[DataLog] Failed to read log file {log_file_path}: {e}")
        return None


async def delete_logs_for_data_source(
    data_source_id: int,
    db: AsyncSession | None = None,
) -> int:
    """
    Delete all log entries and files for a data source.
    
    This function is called when a data source is deleted (cascade delete).
    Note: Database cascade delete handles DB entries automatically,
    but log files must be deleted manually.
    
    Args:
        data_source_id: ID of the data source
        db: Database session (creates new if not provided)
    
    Returns:
        Number of log files deleted
    """
    close_db = False
    if db is None:
        db = await AsyncSessionLocal().__aenter__()
        close_db = True
    
    try:
        # Get all log UUIDs for this data source
        stmt = select(DataSourceLog.log_file_uuid).where(
            DataSourceLog.data_source_id == data_source_id
        )
        result = await db.execute(stmt)
        log_uuids = list(result.scalars().all())
        
        # Delete log files
        log_dir = get_log_directory()
        deleted_count = 0
        
        for log_uuid in log_uuids:
            log_file_path = log_dir / str(log_uuid)
            try:
                if log_file_path.exists():
                    log_file_path.unlink()
                    deleted_count += 1
                    logger.debug(f"[DataLog] Deleted log file: {log_file_path}")
            except Exception as e:
                logger.error(f"[DataLog] Failed to delete log file {log_file_path}: {e}")
        
        logger.info(
            f"[DataLog] Deleted {deleted_count} log files for data source {data_source_id}"
        )
        
        return deleted_count
        
    finally:
        if close_db:
            await db.__aexit__(None, None, None)


async def delete_log_files_by_uuids(log_uuids: list[uuid.UUID]) -> int:
    """
    Delete log files by their UUIDs.
    
    This is a helper function for cleanup tasks that only deletes the files,
    not the database entries. Database entries should be deleted separately.
    
    Args:
        log_uuids: List of log file UUIDs to delete
    
    Returns:
        Number of log files successfully deleted
    """
    if not log_uuids:
        return 0
    
    log_dir = get_log_directory()
    deleted_count = 0
    
    for log_uuid in log_uuids:
        log_file_path = log_dir / str(log_uuid)
        try:
            if log_file_path.exists():
                log_file_path.unlink()
                deleted_count += 1
                logger.debug(f"[DataLog] Deleted log file: {log_file_path}")
        except Exception as e:
            logger.error(f"[DataLog] Failed to delete log file {log_file_path}: {e}")
    
    logger.info(f"[DataLog] Deleted {deleted_count} log files from disk")
    
    return deleted_count
