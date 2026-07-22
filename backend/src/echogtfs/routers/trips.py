"""
Realtime trips router.

Provides authenticated endpoints to list and toggle GTFS-RT trips.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from echogtfs.common.security import CurrentUser
from echogtfs.services.database import get_realtime_repository
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.validation.schemas import TripListResponse, TripRead

router = APIRouter()

_Repo = Annotated[RealtimeRepositoryInterface, Depends(get_realtime_repository)]


@router.get("/", response_model=TripListResponse)
async def list_trips(
    _: CurrentUser,
    repository: _Repo,
    page: int = 1,
    limit: int = 20,
    sort: str = "asc",
    search: str = "",
    is_active: bool | None = None,
) -> TripListResponse:
    """List realtime trips with pagination and optional filtering."""
    page = max(1, page)
    limit = max(1, min(100, limit))
    sort = sort.lower() if sort in ["asc", "desc"] else "asc"
    search = search.strip()

    items, total = await repository.list_trips_paginated(
        page=page,
        limit=limit,
        sort=sort,
        search=search,
        is_active=is_active,
    )

    return TripListResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 1,
        items=items,
    )


@router.post("/{trip_id}/toggle-active", response_model=TripRead)
async def toggle_trip_active(
    trip_id: UUID,
    _: CurrentUser,
    repository: _Repo,
) -> TripRead:
    """Toggle the is_active flag of one realtime trip."""
    trip = await repository.toggle_trip_active(trip_id)

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    return trip
