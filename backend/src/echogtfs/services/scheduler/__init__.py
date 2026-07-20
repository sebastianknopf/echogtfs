from __future__ import annotations

from echogtfs.services.scheduler.datasource_scheduler_service import DatasourceSchedulerService
from echogtfs.services.scheduler.intf_datasource_scheduler import DatasourceSchedulerInterface

_datasource_scheduler_service: DatasourceSchedulerInterface | None = None


def set_datasource_scheduler_service(
    datasource_scheduler_service: DatasourceSchedulerInterface,
) -> None:
    """Register the datasource scheduler singleton for application-wide access."""
    global _datasource_scheduler_service
    _datasource_scheduler_service = datasource_scheduler_service


def get_datasource_scheduler_service() -> DatasourceSchedulerInterface:
    """Return the configured datasource scheduler singleton."""
    if _datasource_scheduler_service is None:
        raise RuntimeError("Datasource scheduler service is not initialized")

    return _datasource_scheduler_service


__all__ = [
    "DatasourceSchedulerInterface",
    "DatasourceSchedulerService",
    "set_datasource_scheduler_service",
    "get_datasource_scheduler_service",
]