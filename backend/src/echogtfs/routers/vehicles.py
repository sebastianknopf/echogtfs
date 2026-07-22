"""
Realtime vehicles router.

Provides authenticated endpoints to list and toggle GTFS-RT vehicle positions.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from echogtfs.common.security import CurrentUser
from echogtfs.services.database import get_realtime_repository
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.validation.schemas import VehicleListResponse, VehicleRead

router = APIRouter()

_Repo = Annotated[RealtimeRepositoryInterface, Depends(get_realtime_repository)]


@router.get("/", response_model=VehicleListResponse)
async def list_vehicles(
    _: CurrentUser,
    repository: _Repo,
    page: int = 1,
    limit: int = 200,
    search: str = "",
    is_active: bool | None = None,
) -> VehicleListResponse:
    """List realtime vehicles with pagination and optional filtering."""
    page = max(1, page)
    limit = max(1, min(1000, limit))
    search = search.strip()

    items, total = await repository.list_vehicles_paginated(
        page=page,
        limit=limit,
        search=search,
        is_active=is_active,
    )

    return VehicleListResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 1,
        items=items,
    )


@router.post("/{vehicle_id}/toggle-active", response_model=VehicleRead)
async def toggle_vehicle_active(
    vehicle_id: UUID,
    _: CurrentUser,
    repository: _Repo,
) -> VehicleRead:
    """Toggle the is_active flag of one realtime vehicle."""
    vehicle = await repository.toggle_vehicle_active(vehicle_id)

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )

    return vehicle
