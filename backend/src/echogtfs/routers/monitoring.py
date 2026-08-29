from typing import Annotated

from datetime import date
from fastapi import APIRouter, Depends, Query

from echogtfs.services.database import (
    RealtimeRepositoryInterface,
    GtfsRepositoryInterface,
    SystemRepositoryInterface,
    get_realtime_repository,
    get_gtfs_repository,
    get_system_repository,
)

from echogtfs.services.database.models import AppSetting
from echogtfs.services.conflict.conflict_export_service import ConflictExportService
from echogtfs.enum.gtfs import GtfsImportStatus
from echogtfs.validation.schemas import MonitoringConflictObject, MonitoringDatasourceGroupObject, MonitoringRouteGroupObject, MonitoringStatisticsObject, MonitoringStatisticsRealtimeObject, MonitoringStatisticsRealtimeAlertsObject, MonitoringStatisticsRealtimeTripsObject, MonitoringStatisticsRealtimeVehiclesObject, MonitoringStatisticsStaticObject, MonitoringConflictsResponse, MonitoringStatisticsResponse, MonitoringSystemFiltersObject, MonitoringSystemResponse
from echogtfs.common.security import CurrentPoweruser
from echogtfs._version import __version__

router = APIRouter()

_SystemRepo = Annotated[SystemRepositoryInterface, Depends(get_system_repository)]
_GtfsRepo = Annotated[GtfsRepositoryInterface, Depends(get_gtfs_repository)]
_RealtimeRepo = Annotated[RealtimeRepositoryInterface, Depends(get_realtime_repository)]


def _gtfs_import_status_enum(value: str | None) -> GtfsImportStatus | None:
    if value is None:
        return None

    return GtfsImportStatus(value)


@router.get(
    "/system",
    response_model=MonitoringSystemResponse,
    responses={
        401: {
            "description": "Unauthorized Access",
            "content": {
                "application/json": {
                    "example": {"detail": "error.401_unauthorized"}
                }
            }
        },
        403: {
            "description": "Forbidden Access",
            "content": {
                "application/json": {
                    "example": {"detail": "error.403_permission"}
                }
            }
        }
    }
)
async def system(
    _: CurrentPoweruser,
    system_repository: _SystemRepo,
    gtfs_repository: _GtfsRepo
) -> MonitoringSystemResponse:
    """Returns basic system information and available filter values for the monitoring interface."""
    datasources: list[MonitoringDatasourceGroupObject] = [
        MonitoringDatasourceGroupObject(id=ds.id, name=ds.name) for ds in await system_repository.list_data_sources() if ds.is_active
    ]
    
    routes: list[MonitoringRouteGroupObject] = [
        MonitoringRouteGroupObject(id=route.gtfs_id, short_name=route.short_name, long_name=route.long_name) for route in await gtfs_repository.list_gtfs_routes(query="", limit=10000)
    ]

    response: MonitoringSystemResponse = MonitoringSystemResponse(
        version=__version__,
        status=True,
        filters=MonitoringSystemFiltersObject(
            datasources=datasources,
            routes=routes
        )
    )

    return response


@router.get(
    "/statistics",
    response_model=MonitoringStatisticsResponse,
    responses={
        401: {
            "description": "Unauthorized Access",
            "content": {
                "application/json": {
                    "example": {"detail": "error.401_unauthorized"}
                }
            }
        },
        403: {
            "description": "Forbidden Access",
            "content": {
                "application/json": {
                    "example": {"detail": "error.403_permission"}
                }
            }
        }
    }
)
async def statistics(
    _: CurrentPoweruser,
    system_repository: _SystemRepo,
    gtfs_repository: _GtfsRepo,
    realtime_repository: _RealtimeRepo,
    route_id: str | None = Query(
        None,
        alias="routeId",
        description="ID of the route the results shall be filtered for. If not provided, conflicts from all routes will be returned."
    )
) -> MonitoringStatisticsResponse:
    """Returns an object with statistical information about the static GTFS data and the realtime objects for GTFS-RT."""
    routes: list[MonitoringRouteGroupObject] = [
        MonitoringRouteGroupObject(id=route.gtfs_id, short_name=route.short_name, long_name=route.long_name) for route in await gtfs_repository.list_gtfs_routes(query="", limit=10000)
    ]

    static_statistics: dict[str, int] = await gtfs_repository.list_gtfs_object_statistics()
    static_operation_day_dates: list[date] = await gtfs_repository.list_gtfs_operation_day_dates()

    realtime_statistics: dict[str, any] = await realtime_repository.list_realtime_object_statistics([route_id] if route_id else [r.id for r in routes])
    
    response: MonitoringStatisticsResponse = MonitoringStatisticsResponse(
        statistics=MonitoringStatisticsObject(
            static=MonitoringStatisticsStaticObject(
                last_import_timestamp=await system_repository.get_app_setting(AppSetting.KEY_GTFS_IMPORT_TIME),
                last_import_status=_gtfs_import_status_enum(await system_repository.get_app_setting(AppSetting.KEY_GTFS_IMPORT_STATUS)),
                num_agencies=static_statistics.get("num_agencies", 0),
                num_routes=static_statistics.get("num_routes", 0),
                num_stops=static_statistics.get("num_stops", 0),
                num_trips=static_statistics.get("num_trips", 0),
                operation_day_dates=static_operation_day_dates
            ),
            realtime=MonitoringStatisticsRealtimeObject(
                alerts=MonitoringStatisticsRealtimeAlertsObject(
                    num_alerts=realtime_statistics.get("num_alerts", 0)
                ),
                trips=[
                    MonitoringStatisticsRealtimeTripsObject(
                        route=next((obj for obj in routes if obj.id == id), None),
                        num_running_trips=r.get("num_running_trips", 0),
                        num_realtime_trips=r.get("num_realtime_trips", 0),
                        num_monitored_trips=r.get("num_monitored_trips", 0)
                    )
                    for id, r in realtime_statistics.get("trips", {}).items()
                ],
                vehicles=[
                    MonitoringStatisticsRealtimeVehiclesObject(
                        route=next((obj for obj in routes if obj.id == id), None),
                        num_vehicles=r.get("num_vehicles", 0),
                    )
                    for id, r in realtime_statistics.get("vehicles", {}).items()
                ]
            )
        )
    )

    return response


@router.get(
    "/conflicts",
    response_model=MonitoringConflictsResponse,
    responses={
        401: {
            "description": "Unauthorized Access",
            "content": {
                "application/json": {
                    "example": {"detail": "error.401_unauthorized"}
                }
            }
        },
        403: {
            "description": "Forbidden Access",
            "content": {
                "application/json": {
                    "example": {"detail": "error.403_permission"}
                }
            }
        }
    }
)
async def conflicts(
    _: CurrentPoweruser,
    system_repository: _SystemRepo,
    realtime_repository: _RealtimeRepo,
    data_source_id: int | None = Query(
        None,
        alias="datasourceId",
        description="ID of the data source the results shall be filtered for. If not provided, conflicts from all data sources will be returned."
    )
) -> MonitoringConflictsResponse:
    """Returns an object with the current conflicts in the system."""
    conflict_export_service = ConflictExportService(
        system_repository=system_repository,
        realtime_repository=realtime_repository
    )

    conflicts: list[MonitoringConflictObject] = conflict_export_service.export(datasource_id=data_source_id)

    response: MonitoringConflictsResponse = MonitoringConflictsResponse(
        conflicts=conflicts
    )

    return response