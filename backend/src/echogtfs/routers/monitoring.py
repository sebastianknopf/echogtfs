from typing import Annotated

from fastapi import APIRouter, Depends

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
    "/statistics"
)
async def statistics(
    _: CurrentPoweruser,
    gtfs_repository: _GtfsRepo,
    realtime_repository: _RealtimeRepo,
) -> dict:
    """Returns an object with statistical information about the system."""
    return {"message": "API is running. Statistics will be available soon."}


@router.get(
    "/conflicts"
)
async def conflicts(
    _: CurrentPoweruser,
    gtfs_repository: _GtfsRepo,
    realtime_repository: _RealtimeRepo,
) -> dict:
    """Returns an object with the current conflicts in the system."""
    return {"message": "Current conflicts will be listed here."}