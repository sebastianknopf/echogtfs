"""Data source logging service."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import uuid

from echogtfs.services.database import RepositoryInterface
from echogtfs.services.database.models import DataSourceLog

logger = logging.getLogger("uvicorn")

DEFAULT_LOG_DIR = Path("/var/log/echogtfs/datasources")


class DatalogService:
    """Manages data source request logging and log-file persistence."""

    def __init__(self, repository: RepositoryInterface):
        self._repository = repository

    @staticmethod
    def get_log_directory() -> Path:
        """Return log directory and ensure it exists."""
        log_dir_str = os.getenv("DATASOURCE_LOG_DIR", str(DEFAULT_LOG_DIR))
        log_dir = Path(log_dir_str)
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    async def create_log_entry(
        self,
        data_source_id: int,
        request_url: str,
        response_content: bytes | str,
        request_headers: dict[str, Any] | None = None,
        response_headers: dict[str, Any] | None = None,
        response_mimetype: str | None = None,
        status_code: int | None = None,
    ) -> DataSourceLog:
        """Create a new log entry and persist payload to log file."""
        log_uuid = uuid.uuid4()

        if isinstance(response_content, str):
            content_bytes = response_content.encode("utf-8")
        else:
            content_bytes = response_content

        content_size_before = len(content_bytes)
        logger.info(
            "[DataLog] Preparing to write %s bytes (%.2f KB, %.2f MB) for data source %s",
            content_size_before,
            content_size_before / 1024,
            content_size_before / (1024 * 1024),
            data_source_id,
        )

        log_dir = self.get_log_directory()
        log_file_path = log_dir / str(log_uuid)

        try:
            log_file_path.write_bytes(content_bytes)
            logger.info("[DataLog] Saved log file: %s", log_file_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("[DataLog] Failed to save log file %s: %s", log_file_path, exc)
            raise

        actual_size = log_file_path.stat().st_size

        logger.info(
            "[DataLog] File written successfully. Size on disk: %s bytes (%.2f KB, %.2f MB)",
            actual_size,
            actual_size / 1024,
            actual_size / (1024 * 1024),
        )

        if content_size_before != actual_size:
            logger.warning(
                "[DataLog] Size mismatch! Content size: %s bytes, File size: %s bytes (difference: %s bytes)",
                content_size_before,
                actual_size,
                abs(content_size_before - actual_size),
            )

        request_headers_json = json.dumps(request_headers) if request_headers else None
        response_headers_json = json.dumps(response_headers) if response_headers else None

        log_entry = await self._repository.create_data_source_log(
            data_source_id=data_source_id,
            timestamp=datetime.now(UTC),
            request_url=request_url,
            request_headers=request_headers_json,
            response_headers=response_headers_json,
            response_mimetype=response_mimetype,
            status_code=status_code,
            response_size=actual_size,
            log_file_uuid=log_uuid,
        )

        logger.info(
            "[DataLog] Created log entry %s for data source %s (file: %s)",
            log_entry.id,
            data_source_id,
            log_uuid,
        )

        return log_entry

    async def get_logs_for_data_source(self, data_source_id: int, limit: int = 100) -> list[DataSourceLog]:
        """Return recent log entries for one data source."""
        logs = await self._repository.list_data_source_logs(data_source_id, limit=limit)
        logger.debug("[DataLog] Retrieved %s log entries for data source %s", len(logs), data_source_id)
        
        return logs

    async def get_log_content(self, log_uuid: uuid.UUID) -> bytes | None:
        """Read one log file payload by UUID."""
        log_file_path = self.get_log_directory() / str(log_uuid)

        try:
            if log_file_path.exists():
                return log_file_path.read_bytes()
            
            logger.warning("[DataLog] Log file not found: %s", log_file_path)
            
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("[DataLog] Failed to read log file %s: %s", log_file_path, exc)
            
            return None

    async def delete_logs_for_data_source(self, data_source_id: int) -> int:
        """Delete all log files and DB log rows for one data source."""
        log_uuids = await self._repository.list_data_source_log_uuids_for_data_source(data_source_id)
        deleted_count = await self.delete_log_files_by_uuids(log_uuids)
        await self._repository.delete_data_source_logs_for_data_source(data_source_id)

        logger.info("[DataLog] Deleted %s log files for data source %s", deleted_count, data_source_id)
        
        return deleted_count

    async def delete_log_files_by_uuids(self, log_uuids: list[uuid.UUID]) -> int:
        """Delete log files by UUID list."""
        if not log_uuids:
            return 0

        log_dir = self.get_log_directory()
        deleted_count = 0

        for log_uuid in log_uuids:
            log_file_path = log_dir / str(log_uuid)
            try:
                if log_file_path.exists():
                    log_file_path.unlink()
                    deleted_count += 1
                    logger.debug("[DataLog] Deleted log file: %s", log_file_path)
            
            except Exception as exc:  # noqa: BLE001
                logger.error("[DataLog] Failed to delete log file %s: %s", log_file_path, exc)

        logger.info("[DataLog] Deleted %s log files from disk", deleted_count)
        
        return deleted_count
