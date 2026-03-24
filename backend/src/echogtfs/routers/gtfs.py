"""GTFS router.

Endpoints:
    GET  /api/gtfs/status      – feed URL + import status (admin)
    PUT  /api/gtfs/feed-url    – persist feed URL (admin)
    POST /api/gtfs/import      – trigger background import (admin) → 202
    GET  /api/gtfs/agencies    – list agencies (authenticated)
    GET  /api/gtfs/stops       – search stops   (authenticated)
    GET  /api/gtfs/routes      – search routes  (authenticated)
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.database import get_db
from echogtfs.models import AppSetting, GtfsAgency, GtfsRoute, GtfsStop
from echogtfs.schemas import (
    AgencyRead,
    GtfsFeedConfig,
    GtfsStatusRead,
    RouteRead,
    StopRead,
)
from echogtfs.security import CurrentSuperuser, CurrentUser
from echogtfs.services.gtfs_import import (
    KEY_FEED_URL,
    KEY_MSG,
    KEY_STATUS,
    KEY_TIME,
    KEY_CRON,
    STATUS_IDLE,
    STATUS_RUNNING,
    run_import_task,
    schedule_import_from_cron,
)

router = APIRouter()

_DB = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("/status", response_model=GtfsStatusRead)
async def get_status(_: CurrentSuperuser, db: _DB) -> GtfsStatusRead:
    """Return current feed URL, cron, and last import state."""
    rows: dict[str, str] = {}
    result = await db.execute(
        select(AppSetting).where(
            AppSetting.key.in_([KEY_FEED_URL, KEY_STATUS, KEY_TIME, KEY_MSG, KEY_CRON])
        )
    )
    for row in result.scalars():
        rows[row.key] = row.value

    cron_val = rows.get(KEY_CRON)
    return GtfsStatusRead(
        feed_url=rows.get(KEY_FEED_URL, ""),
        cron=cron_val if cron_val not in (None, "") else None,
        status=rows.get(KEY_STATUS, STATUS_IDLE),
        imported_at=rows.get(KEY_TIME),
        message=rows.get(KEY_MSG),
    )



# ---------------------------------------------------------------------------
# Trigger import
# ---------------------------------------------------------------------------

@router.post("/import", status_code=status.HTTP_202_ACCEPTED)
async def trigger_import(
    _: CurrentSuperuser,
    db: _DB,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    Enqueue a background import.  Returns 202 immediately; poll /status for
    progress.  Returns 409 if an import is already running.
    """
    # Check whether an import is already in progress
    row = await db.get(AppSetting, KEY_STATUS)
    if row is not None and row.value == STATUS_RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ein Import läuft bereits.",
        )

    background_tasks.add_task(run_import_task)
    return {"status": STATUS_RUNNING}


# ---------------------------------------------------------------------------
# Feed URL & Cron config
# ---------------------------------------------------------------------------

from pydantic import BaseModel

class GtfsConfigUpdate(BaseModel):
    feed_url: str | None = None
    cron: str | None = None

@router.put("/feed-url", status_code=200)
async def update_feed_url(
    _: CurrentSuperuser,
    db: _DB,
    data: GtfsConfigUpdate,
) -> dict[str, str]:
    """Update GTFS feed URL and/or cron expression."""
    if data.feed_url:
        await db.merge(AppSetting(key=KEY_FEED_URL, value=data.feed_url))
    if data.cron is not None:
        await db.merge(AppSetting(key=KEY_CRON, value=data.cron))
    await db.commit()
    if data.cron is not None:
        await schedule_import_from_cron(db)
    return {"feed_url": data.feed_url or "", "cron": data.cron or ""}


# ---------------------------------------------------------------------------
# Entity listing
# ---------------------------------------------------------------------------

@router.get("/agencies", response_model=list[AgencyRead])
async def list_agencies(_: CurrentUser, db: _DB) -> list[GtfsAgency]:
    result = await db.execute(
        select(GtfsAgency).order_by(GtfsAgency.name)
    )
    return list(result.scalars())


@router.get("/stops", response_model=list[StopRead])
async def list_stops(
    _: CurrentUser,
    db: _DB,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[GtfsStop]:
    stmt = select(GtfsStop).order_by(GtfsStop.name)
    if q:
        stmt = stmt.where(GtfsStop.name.ilike(f"%{q}%"))
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars())


@router.get("/routes", response_model=list[RouteRead])
async def list_routes(
    _: CurrentUser,
    db: _DB,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[GtfsRoute]:
    stmt = select(GtfsRoute).order_by(GtfsRoute.short_name, GtfsRoute.long_name)
    if q:
        stmt = stmt.where(
            GtfsRoute.short_name.ilike(f"%{q}%")
            | GtfsRoute.long_name.ilike(f"%{q}%")
        )
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars())
