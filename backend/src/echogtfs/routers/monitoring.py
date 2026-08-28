from typing import Annotated

from echogtfs.validation.schemas import MonitoredStatisticsObject, MonitoredStatisticsRealtimeObject, MonitoredStatisticsRealtimeAlertsObject, MonitoredStatisticsSystemObject, MonitoredStatisticsStaticObject, MonitoringConflictsResponse, MonitoringStatisticsResponse
from fastapi import APIRouter, Depends, Query

from echogtfs.services.database import (
    RealtimeRepositoryInterface,
    GtfsRepositoryInterface,
    get_realtime_repository,
    get_gtfs_repository,
)

from echogtfs.common.security import CurrentPoweruser

router = APIRouter()

_GtfsRepo = Annotated[GtfsRepositoryInterface, Depends(get_gtfs_repository)]
_RealtimeRepo = Annotated[RealtimeRepositoryInterface, Depends(get_realtime_repository)]


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
    gtfs_repository: _GtfsRepo,
    realtime_repository: _RealtimeRepo,
    route_id: str | None = Query(
        None,
        alias="routeId",
        description="ID of the route the results shall be filtered for. If not provided, conflicts from all routes will be returned."
    )
) -> MonitoringStatisticsResponse:
    """Returns an object with statistical information about the system."""
    response: MonitoringStatisticsResponse = MonitoringStatisticsResponse(
        statistics=MonitoredStatisticsObject(
            system=MonitoredStatisticsSystemObject(
                datasources=[]
            ),
            static=MonitoredStatisticsStaticObject(
                last_import_timestamp=None,
                last_import_status=None,
                num_agencies=0,
                num_routes=0,
                num_stops=0,
                num_trips=0,
                routes=[],
                operation_day_dates=[]
            ),
            realtime=MonitoredStatisticsRealtimeObject(
                alerts=MonitoredStatisticsRealtimeAlertsObject(
                    num_alerts=0
                ),
                trips=[],
                vehicles=[]
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
    gtfs_repository: _GtfsRepo,
    realtime_repository: _RealtimeRepo,
    data_source_id: int | None = Query(
        None,
        alias="datasourceId",
        description="ID of the data source the results shall be filtered for. If not provided, conflicts from all data sources will be returned."
    )
) -> MonitoringConflictsResponse:
    """Returns an object with the current conflicts in the system."""
    response: MonitoringConflictsResponse = MonitoringConflictsResponse(
        conflicts=[]
    )

    return response