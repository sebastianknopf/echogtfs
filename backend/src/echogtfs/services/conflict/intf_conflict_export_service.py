from __future__ import annotations

from abc import ABC, abstractmethod

from echogtfs.validation.schemas import MonitoringConflictObject


class ConflictExportServiceInterface(ABC):

    @abstractmethod
    async def export(self, datasource_id: int | None = None) -> list[MonitoringConflictObject]:
        """Exports a list of conflicts currently present in the system. Can be restricted to a specific datasource if provided."""
        raise NotImplementedError