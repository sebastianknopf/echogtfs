"""
Dashboard router.

Provides one authenticated endpoint with dashboard counters and GTFS-RT endpoint URLs.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import exists, func, select

from echogtfs.common.security import CurrentUser
from echogtfs.services.database import get_realtime_repository, get_system_repository
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.database.models import AppSetting
from echogtfs.validation.schemas import DashboardRead

router = APIRouter()

_Repo = Annotated[RealtimeRepositoryInterface, Depends(get_realtime_repository)]
_SystemRepo = Annotated[SystemRepositoryInterface, Depends(get_system_repository)]

_DEFAULT_SERVICE_ALERTS_PATH = "realtime/service-alerts.pbf"
_DEFAULT_TRIP_UPDATES_PATH = "realtime/trip-updates.pbf"
_DEFAULT_VEHICLE_POSITIONS_PATH = "realtime/vehicle-positions.pbf"


def _normalize_endpoint_path(path_value: str) -> str:
    normalized = (path_value or "").strip()
    if not normalized:
        return ""
    return normalized.lstrip("/")


def _build_public_api_url(request: Request, endpoint_path: str) -> str:
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    return f"{base_url}/api/{endpoint_path}"


@router.get("/", response_model=DashboardRead, include_in_schema=False)
async def get_dashboard(
    request: Request,
    _: CurrentUser,
    repository: _Repo,
    system_repository: _SystemRepo,
) -> DashboardRead:
    """Return dashboard counters and configured GTFS-RT endpoint URLs."""
    app_settings = await system_repository.get_all_app_settings()

    service_alerts_path = _normalize_endpoint_path(
        app_settings.get(AppSetting.KEY_GTFS_RT_SERVICE_ALERTS_PATH, _DEFAULT_SERVICE_ALERTS_PATH)
    )
    trip_updates_path = _normalize_endpoint_path(
        app_settings.get(AppSetting.KEY_GTFS_RT_TRIP_UPDATES_PATH, _DEFAULT_TRIP_UPDATES_PATH)
    )
    vehicle_positions_path = _normalize_endpoint_path(
        app_settings.get(AppSetting.KEY_GTFS_RT_VEHICLE_POSITIONS_PATH, _DEFAULT_VEHICLE_POSITIONS_PATH)
    )

    alerts_active, alerts_inactive = await repository.count_service_alerts_by_active()
    trips_active, trips_monitored, trips_inactive = await repository.count_trip_updates_by_status()
    vehicles_active, vehicles_inactive = await repository.count_vehicle_positions_by_active()

    return DashboardRead(
        counts={
            "service_alerts": {
                "active": alerts_active,
                "inactive": alerts_inactive,
            },
            "trip_updates": {
                "active": trips_active,
                "monitored": trips_monitored,
                "inactive": trips_inactive,
            },
            "vehicle_positions": {
                "active": vehicles_active,
                "inactive": vehicles_inactive,
            },
        },
        endpoints={
            "service_alerts": {
                "path": service_alerts_path,
                "url": _build_public_api_url(request, service_alerts_path),
            },
            "trip_updates": {
                "path": trip_updates_path,
                "url": _build_public_api_url(request, trip_updates_path),
            },
            "vehicle_positions": {
                "path": vehicle_positions_path,
                "url": _build_public_api_url(request, vehicle_positions_path),
            },
        },
    )
