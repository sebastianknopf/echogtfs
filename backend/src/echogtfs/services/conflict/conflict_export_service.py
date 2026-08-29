from __future__ import annotations

from echogtfs.enum.conflicts import ConflictType
from echogtfs.services.conflict.intf_conflict_export_service import ConflictExportServiceInterface
from echogtfs.services.database.realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.system_repository import SystemRepositoryInterface
from echogtfs.validation.schemas import MonitoringConflictObject


class ConflictExportService(ConflictExportServiceInterface):

    def __init__(self, system_repository: SystemRepositoryInterface, realtime_repository: RealtimeRepositoryInterface):
        self._system_repository = system_repository
        self._realtime_repository = realtime_repository

    def export(self, datasource_id: int | None = None) -> list[MonitoringConflictObject]:
        return []