from typing import Annotated

from fastapi import APIRouter, Depends

from echogtfs.services.database import (
    RealtimeRepositoryInterface,
    get_realtime_repository,
)

from echogtfs.common.security import CurrentPoweruser

router = APIRouter()

_RealtimeRepo = Annotated[RealtimeRepositoryInterface, Depends(get_realtime_repository)]


@router.get(
    "/future"
)
async def future(
    _: CurrentPoweruser,
    repository: _RealtimeRepo,
) -> dict:
    """Returns a simple message indicating that the API is running and future monitoring features are coming soon."""
    return {"message": "API is running. Future monitoring features coming soon."}