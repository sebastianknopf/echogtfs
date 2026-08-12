"""
Realtime trips router.

Provides authenticated endpoints to list and toggle GTFS-RT trips.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from echogtfs.common.security import CurrentUser
from echogtfs.services.database import get_gtfs_repository, get_realtime_repository
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.validation.schemas import TripListResponse, TripRead

router = APIRouter()

_Repo = Annotated[RealtimeRepositoryInterface, Depends(get_realtime_repository)]
_GtfsRepo = Annotated[GtfsRepositoryInterface, Depends(get_gtfs_repository)]


async def _load_gtfs_entity_names(repository: GtfsRepositoryInterface) -> dict[str, dict[str, str]]:
    """Load GTFS route and stop IDs and names for response enrichment."""
    entity_names = {
        "route": {},
        "stop": {},
    }

    routes = await repository.list_gtfs_routes(query="", limit=100000)
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
            entity_names["route"][gtfs_id] = name

    # Load stops
    stops = await repository.list_gtfs_stops(query="", limit=100000)
    entity_names["stop"] = {stop.gtfs_id: stop.name for stop in stops}

    return entity_names


def _filter_trips_with_stop_events(trips: list[dict]) -> list[dict]:
    """Return only trips that contain at least one stop event."""
    return [
        trip for trip in trips
        if isinstance(trip.get("stop_events"), list) and len(trip.get("stop_events", [])) > 0
    ]


def _build_trip_response_payload(trip: object) -> dict:
    """Convert a repository trip object into a response payload, preserving the linked vehicle."""
    trip_read = TripRead.model_validate(trip)
    trip_dict = trip_read.model_dump()

    vehicle = getattr(trip, "vehicle", None)
    if vehicle is not None:
        trip_dict["vehicle"] = {
            "vehicle_label": getattr(vehicle, "vehicle_label", None),
            "vehicle_license_plate": getattr(vehicle, "vehicle_license_plate", None),
            "vehicle_id": getattr(vehicle, "vehicle_id", None),
        }
    else:
        trip_dict["vehicle"] = None

    return trip_dict


def _enrich_trips_with_entity_names(
    trips: list[dict],
    entity_names: dict[str, dict[str, str]],
) -> None:
    """Enrich trip dicts with route/stop names and aggregated validity."""
    for trip in trips:
        if trip.get("route_id"):
            trip["route_name"] = entity_names["route"].get(trip["route_id"], trip["route_id"])

        vehicle = trip.get("vehicle")
        if vehicle is not None:
            vehicle_display_text = None
            if vehicle.get("vehicle_label"):
                vehicle_display_text = vehicle.get("vehicle_label")
            elif vehicle.get("vehicle_license_plate"):
                vehicle_display_text = vehicle.get("vehicle_license_plate")
            elif vehicle.get("vehicle_id"):
                vehicle_display_text = vehicle.get("vehicle_id")

            trip["vehicle_display_text"] = vehicle_display_text
        else:
            trip["vehicle_display_text"] = None

        if trip.get("scheduled_start_stop_id") and trip.get("scheduled_start_stop_name") is None:
            trip["scheduled_start_stop_name"] = entity_names["stop"].get(
                trip["scheduled_start_stop_id"],
                trip["scheduled_start_stop_id"],
            )

        if trip.get("scheduled_end_stop_id") and trip.get("scheduled_end_stop_name") is None:
            trip["scheduled_end_stop_name"] = entity_names["stop"].get(
                trip["scheduled_end_stop_id"],
                trip["scheduled_end_stop_id"],
            )

        has_invalid_stop_event = False
        for stop_event in trip.get("stop_events", []):
            if stop_event.get("stop_id"):
                stop_event["stop_name"] = entity_names["stop"].get(stop_event["stop_id"], stop_event["stop_id"])
            if stop_event.get("is_valid") is False:
                has_invalid_stop_event = True

        if has_invalid_stop_event:
            trip["is_valid"] = False


@router.get("/", response_model=TripListResponse)
async def list_trips(
    _: CurrentUser,
    repository: _Repo,
    gtfs_repository: _GtfsRepo,
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

    response = TripListResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 1,
        items=items,
    )

    entity_names = await _load_gtfs_entity_names(gtfs_repository)
    response_dict = response.model_dump()
    response_items = _filter_trips_with_stop_events(
        [_build_trip_response_payload(trip) for trip in items]
    )
    response_dict["items"] = response_items
    _enrich_trips_with_entity_names(response_items, entity_names)

    response_dict["total"] = len(response_items)
    response_dict["total_pages"] = (len(response_items) + limit - 1) // limit if response_items else 1

    return response_dict


@router.post("/{trip_id}/toggle-active", response_model=TripRead)
async def toggle_trip_active(
    trip_id: UUID,
    _: CurrentUser,
    repository: _Repo,
    gtfs_repository: _GtfsRepo,
) -> TripRead:
    """Toggle the is_active flag of one realtime trip."""
    trip = await repository.toggle_trip_active(trip_id)

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    trip_dict = _build_trip_response_payload(trip)

    entity_names = await _load_gtfs_entity_names(gtfs_repository)
    _enrich_trips_with_entity_names([trip_dict], entity_names)

    return trip_dict
