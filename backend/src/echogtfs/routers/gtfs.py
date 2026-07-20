"""GTFS router.

Endpoints:
    GET  /api/gtfs/status      – feed URL + import status (admin)
    GET  /api/gtfs/agencies    – list agencies (authenticated)
    GET  /api/gtfs/stops       – search stops   (authenticated)
    GET  /api/gtfs/routes      – search routes  (authenticated)
    POST /api/gtfs/import      – trigger background import (admin) → 202
    PUT  /api/gtfs/feed-url    – persist feed URL (admin)
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from echogtfs.services.database import get_gtfs_repository, get_system_repository
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.database.models import GtfsAgency, GtfsRoute, GtfsStop
from echogtfs.common.security import CurrentUser, CurrentPoweruser
from echogtfs.services.gtfs import (
    GtfsImportInterface,
    GtfsImportService,
)
from echogtfs.validation.schemas import AgencyRead, GtfsStatusRead, RouteRead, StopRead, GtfsConfigUpdate


router = APIRouter()

_Repo = Annotated[SystemRepositoryInterface, Depends(get_system_repository)]
_GtfsRepo = Annotated[GtfsRepositoryInterface, Depends(get_gtfs_repository)]


def create_gtfs_import_service(repository: _Repo, gtfs_repository: _GtfsRepo) -> GtfsImportInterface:
    """Create a GTFS import service instance for the current dependency scope."""
    return GtfsImportService(repository, gtfs_repository)


_GtfsImport = Annotated[GtfsImportInterface, Depends(create_gtfs_import_service)]


@router.get("/status", response_model=GtfsStatusRead)
async def get_status(_: CurrentPoweruser, service: _GtfsImport) -> GtfsStatusRead:
    """Return current feed URL, cron, and last import state."""
    payload = await service.get_status()
    return GtfsStatusRead(**payload)


@router.get("/agencies", response_model=list[AgencyRead])
async def list_agencies(_: CurrentUser, repository: _GtfsRepo) -> list[GtfsAgency]:
    return await repository.list_gtfs_agencies()


@router.get("/stops", response_model=list[StopRead])
async def list_stops(
    _: CurrentUser,
    repository: _GtfsRepo,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[GtfsStop]:
    return await repository.list_gtfs_stops(query=q, limit=limit)


@router.get("/routes", response_model=list[RouteRead])
async def list_routes(
    _: CurrentUser,
    repository: _GtfsRepo,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[GtfsRoute]:
    return await repository.list_gtfs_routes(query=q, limit=limit)


@router.post("/import", status_code=status.HTTP_202_ACCEPTED)
async def trigger_import(
    _: CurrentPoweruser,
    background_tasks: BackgroundTasks,
    service: _GtfsImport,
) -> dict[str, str]:
    """
    Enqueue a background import.  Returns 202 immediately; poll /status for
    progress.  Returns 409 if an import is already running.
    """
    # Check whether an import is already in progress
    if await service.is_import_running():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An import is already running.",
        )

    background_tasks.add_task(service.run_import_task)
    return {"status": GtfsImportService.STATUS_RUNNING}


@router.put("/feed-url", status_code=200)
async def update_feed_url(
    _: CurrentPoweruser,
    data: GtfsConfigUpdate,
    service: _GtfsImport,
) -> dict[str, str]:
    """Update GTFS feed URL and/or cron expression."""
    return await service.update_configuration(feed_url=data.feed_url, cron=data.cron)
