from __future__ import annotations

from hashlib import sha256
from datetime import datetime

from echogtfs.enum.conflicts import ConflictType
from echogtfs.services.conflict.intf_conflict_export_service import ConflictExportServiceInterface
from echogtfs.services.database.realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.system_repository import SystemRepositoryInterface
from echogtfs.validation.schemas import MonitoringConflictObject, MonitoringDataSourceGroupObject


class ConflictExportService(ConflictExportServiceInterface):

    def __init__(self, system_repository: SystemRepositoryInterface, realtime_repository: RealtimeRepositoryInterface):
        self._system_repository = system_repository
        self._realtime_repository = realtime_repository

    def export(self, datasource_id: int | None = None) -> list[MonitoringConflictObject]:
        results: list[MonitoringConflictObject] = []

        # select datasource failures
        for ds in self._system_repository.list_data_sources_with_failures(min_num_failures=5):
            if datasource_id is None or ds.id == datasource_id:
                last_failure: datetime | None = ds.logs[-1].timestamp if len(ds.logs) > 0 else None

                results.append(MonitoringConflictObject(
                    id=self._unique_conflict_id(datasource_id=ds.id, conflict_type=ConflictType.DATASOURCE_FAILURE, last_failure=last_failure),
                    timestamp=last_failure,
                    conflict_type=ConflictType.DATASOURCE_FAILURE,
                    message=ConflictType.DATASOURCE_FAILURE.name,
                    datasource=MonitoringDataSourceGroupObject(
                        id=ds.id,
                        name=ds.name,
                    ),
                    properties={
                        "datasource_id": ds.id,
                        "last_status": ds.logs[-1].status if len(ds.logs) > 0 else None,
                        "last_failure": last_failure
                    }
                ))

        return results

    def _unique_conflict_id(self, **kwargs) -> str:
        """Generate a unique conflict identifier based on provided keyword arguments."""

        return sha256("_".join(f"{key}={value}" for key, value in sorted(kwargs.items())).encode()).hexdigest()