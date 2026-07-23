"""
Realtime vehicles router.

Provides authenticated endpoints to list and toggle GTFS-RT vehicle positions.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from echogtfs.common.security import CurrentUser
from echogtfs.services.database import get_gtfs_repository, get_realtime_repository
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.validation.schemas import VehicleListResponse, VehicleRead

router = APIRouter()

_Repo = Annotated[RealtimeRepositoryInterface, Depends(get_realtime_repository)]
_GtfsRepo = Annotated[GtfsRepositoryInterface, Depends(get_gtfs_repository)]


async def _load_gtfs_route_names(repository: GtfsRepositoryInterface) -> dict[str, str]:
    """Load GTFS route ID-to-name mapping for vehicle line enrichment."""
    routes = await repository.list_gtfs_routes(query="", limit=100000)
    route_names: dict[str, str] = {}

    for route in routes:
        gtfs_id = route.gtfs_id
        short_name = route.short_name
        long_name = route.long_name

        if short_name and long_name:
            name = f"{short_name} - {long_name}"
        elif short_name:
            name = short_name
        elif long_name:
            name = long_name
        else:
            name = None

        if name:
            route_names[gtfs_id] = name

    return route_names


def _enrich_vehicles_with_route_names(vehicles: list[dict], route_names: dict[str, str]) -> None:
    """Enrich vehicle dicts with resolved trip route names (fallback to route_id)."""
    for vehicle in vehicles:
        trip = vehicle.get("trip")
        if not trip:
            continue

        route_id = trip.get("route_id")
        if route_id:
            trip["route_name"] = route_names.get(route_id, route_id)


def _apply_effective_vehicle_validity(
    vehicles: list[dict],
    trip_ids_with_invalid_stop_events: set[str],
) -> None:
    """Set effective trip and vehicle validity including stop-event cascade."""
    for vehicle in vehicles:
        trip = vehicle.get("trip")
        if not trip:
            continue

        trip_id = trip.get("trip_id")
        has_invalid_stop_event = bool(trip_id and trip_id in trip_ids_with_invalid_stop_events)
        trip_is_valid = trip.get("is_valid") is not False

        if has_invalid_stop_event:
            trip_is_valid = False
            trip["is_valid"] = False

        if not trip_is_valid:
            vehicle["is_valid"] = False


@router.get("/", response_model=VehicleListResponse)
async def list_vehicles(
    _: CurrentUser,
    repository: _Repo,
    gtfs_repository: _GtfsRepo,
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

    response = VehicleListResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 1,
        items=items,
    )

    route_names = await _load_gtfs_route_names(gtfs_repository)
    response_dict = response.model_dump()
    _enrich_vehicles_with_route_names(response_dict["items"], route_names)

    trip_ids = [
        item["trip"]["trip_id"]
        for item in response_dict["items"]
        if item.get("trip") and item["trip"].get("trip_id")
    ]
    
    trip_ids_with_invalid_stop_events = await repository.list_trip_ids_with_invalid_stop_events(trip_ids)
    _apply_effective_vehicle_validity(response_dict["items"], trip_ids_with_invalid_stop_events)

    return response_dict


@router.post("/{vehicle_id}/toggle-active", response_model=VehicleRead)
async def toggle_vehicle_active(
    vehicle_id: UUID,
    _: CurrentUser,
    repository: _Repo,
    gtfs_repository: _GtfsRepo,
) -> VehicleRead:
    """Toggle the is_active flag of one realtime vehicle."""
    vehicle = await repository.toggle_vehicle_active(vehicle_id)

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found",
        )

    vehicle_read = VehicleRead.model_validate(vehicle)
    vehicle_dict = vehicle_read.model_dump()

    route_names = await _load_gtfs_route_names(gtfs_repository)
    _enrich_vehicles_with_route_names([vehicle_dict], route_names)

    trip_ids = [vehicle_dict["trip"]["trip_id"]] if vehicle_dict.get("trip") and vehicle_dict["trip"].get("trip_id") else []
    trip_ids_with_invalid_stop_events = await repository.list_trip_ids_with_invalid_stop_events(trip_ids)
    _apply_effective_vehicle_validity([vehicle_dict], trip_ids_with_invalid_stop_events)

    return vehicle_dict
