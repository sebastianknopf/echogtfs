from __future__ import annotations

import csv
import io
from datetime import datetime
from enum import Enum

from echogtfs.services.conflict.conflict_export_service import ConflictExportService
from echogtfs.validation.schemas import MonitoringConflictObject


class ConflictCsvExportService(ConflictExportService):

    HEADER = ["ID", "Code", "Message", "DataSourceID", "Properties"]

    async def export_csv(
        self,
        filter_datasource_id: int | None = None,
        filter_messages_or_codes: list[str | int] | None = None,
    ) -> str:
        """Export conflicts as CSV, optionally restricted to matching messages or codes."""
        conflicts = await self.export(filter_datasource_id=filter_datasource_id)
        if filter_messages_or_codes:
            filters = {self._format_value(value) for value in filter_messages_or_codes}
            conflicts = [
                conflict for conflict in conflicts
                if conflict.message in filters or self._format_value(conflict.code) in filters
            ]

        return self.to_csv(conflicts)

    def to_csv(self, conflicts: list[MonitoringConflictObject]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        writer.writerow(self.HEADER)

        for conflict in conflicts:
            row = [
                conflict.id,
                self._format_value(conflict.code),
                conflict.message,
                conflict.datasource.id,
            ]
            
            for key, value in conflict.properties.items():
                row.append(key)
                row.append(self._format_value(value))
            
            writer.writerow(row)

        return buffer.getvalue()

    @staticmethod
    def _format_value(value) -> str:
        if value is None:
            return ""
        if isinstance(value, Enum):
            return str(value.value)
        if isinstance(value, datetime):
            return value.isoformat()
        
        return str(value)
