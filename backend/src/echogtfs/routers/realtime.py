"""
GTFS-Realtime ServiceAlerts endpoint.

Exports service alerts as GTFS-RT protobuf or JSON format.
This endpoint is public by default, but can be protected via Basic Auth
if credentials are configured in settings.
"""

import base64
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from echogtfs.services.database import get_system_repository
from echogtfs.services.database.models import AppSetting
from echogtfs.services.gtfsrt.gtfs_realtime_service_alerts_export_service import GtfsRealtimeServiceAlertsExportService
from echogtfs.services.security import get_security_service

router = APIRouter()


async def _get_gtfs_rt_settings() -> tuple[str, str, str]:
    """Load GTFS-RT path and optional basic-auth credentials from repository."""
    repository = get_system_repository()
    rows = await repository.get_all_app_settings()
    
    return (
        rows.get(AppSetting.KEY_GTFS_RT_PATH, "realtime/service-alerts.pbf"),
        rows.get(AppSetting.KEY_GTFS_RT_USERNAME, ""),
        rows.get(AppSetting.KEY_GTFS_RT_PASSWORD, ""),
    )


async def check_gtfs_rt_auth(request: Request) -> None:
    """
    Optional Basic Auth for GTFS-RT endpoint.
    
    Checks credentials only if both username and password are configured in settings.
    Raises 401 if auth is required but invalid.
    """
    _, configured_username, hashed_password = await _get_gtfs_rt_settings()
    
    # If no credentials configured, allow access
    if not configured_username or not hashed_password:
        return
    
    # Credentials are configured, require Basic Auth
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    # Decode and verify credentials
    try:
        encoded = auth_header[6:]  # Remove "Basic " prefix
        decoded = base64.b64decode(encoded).decode("utf-8")
        provided_username, _, password = decoded.partition(":")
        
        if provided_username != configured_username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        
        if not get_security_service().verify_password(password, hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/{path:path}")
async def get_service_alerts(
    path: str,
    request: Request,
    _auth: Annotated[None, Depends(check_gtfs_rt_auth)],
    json_format: Annotated[str | None, Query(alias="json")] = None,
    debug_format: Annotated[str | None, Query(alias="debug")] = None,
) -> Response:
    """
    Export GTFS-Realtime ServiceAlerts.
    
    Returns active service alerts in GTFS-RT protobuf format (default)
    or JSON format when ?json or ?debug parameter is present.
    
    The endpoint path is configurable via settings. Authentication is
    optional and only enforced if credentials are configured.
    
    Args:
        path: Requested path (must match configured gtfs_rt_path)
        request: HTTP request for auth checking
        _auth: Auth dependency (automatically checks if needed)
        json_format: If present (query param ?json), return JSON instead of protobuf
        debug_format: If present (query param ?debug), return JSON instead of protobuf
        
    Returns:
        Response with either application/x-protobuf or application/json content
    """
    # Load configured path from repository settings
    configured_path_value, _, _ = await _get_gtfs_rt_settings()
    
    # Normalize paths for comparison (remove leading/trailing slashes)
    configured_path = configured_path_value.strip('/')
    requested_path = path.strip('/')
    
    # Return 404 if path doesn't match
    if requested_path != configured_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found"
        )

    # define export service instance
    export_service = GtfsRealtimeServiceAlertsExportService(get_system_repository())
    
    # Return as JSON or protobuf
    # If ?json or ?debug is present (even without value), return JSON
    if json_format is not None or debug_format is not None:
        json_content = await export_service.export_json()
        
        return Response(
            content=json_content,
            media_type="application/json",
        )
    else:
        protobuf_content = await export_service.export_protobuf()
        
        return Response(
            content=protobuf_content,
            media_type="application/x-protobuf",
        )
