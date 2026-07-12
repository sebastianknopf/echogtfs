"""
GTFS-Realtime ServiceAlerts endpoint.

Exports service alerts as GTFS-RT protobuf or JSON format.
This endpoint is public by default, but can be protected via Basic Auth
if credentials are configured in settings.
"""

import base64
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.database import get_db
from echogtfs.services.database import get_repository
from echogtfs.services.gtfsrt.gtfs_realtime_service_alerts_export_service import GtfsRealtimeServiceAlertsExportService
from echogtfs.routers.settings import _load as load_settings
from echogtfs.security import verify_password

router = APIRouter()

# Simple in-memory cache for GTFS-RT feed
_feed_cache = {
    "protobuf": None,
    "json": None,
    "timestamp": 0,
    "ttl": 30,  # Cache TTL in seconds
}


def invalidate_gtfs_rt_cache() -> None:
    """
    Invalidate the GTFS-RT feed cache.
    
    Call this function whenever alerts are created, updated, or deleted
    to ensure clients get fresh data immediately.
    """
    _feed_cache["protobuf"] = None
    _feed_cache["json"] = None
    _feed_cache["timestamp"] = 0


async def check_gtfs_rt_auth(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    """
    Optional Basic Auth for GTFS-RT endpoint.
    
    Checks credentials only if both username and password are configured in settings.
    Raises 401 if auth is required but invalid.
    """
    settings = await load_settings(db)
    
    # If no credentials configured, allow access
    if not settings.gtfs_rt_username or not settings.gtfs_rt_password:
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
        username, _, password = decoded.partition(":")
        
        if username != settings.gtfs_rt_username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        
        if not verify_password(password, settings.gtfs_rt_password):
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
    db: Annotated[AsyncSession, Depends(get_db)],
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
        db: Database session
        _auth: Auth dependency (automatically checks if needed)
        json_format: If present (query param ?json), return JSON instead of protobuf
        debug_format: If present (query param ?debug), return JSON instead of protobuf
        
    Returns:
        Response with either application/x-protobuf or application/json content
    """
    # Load settings to check if the requested path matches configuration
    settings = await load_settings(db)
    
    # Normalize paths for comparison (remove leading/trailing slashes)
    configured_path = settings.gtfs_rt_path.strip('/')
    requested_path = path.strip('/')
    
    # Return 404 if path doesn't match
    if requested_path != configured_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found"
        )
    
    # Check cache validity
    current_time = time.time()
    cache_valid = (current_time - _feed_cache["timestamp"]) < _feed_cache["ttl"]

    # Return cached response if valid
    if cache_valid:
        if (json_format is not None or debug_format is not None) and _feed_cache["json"] is not None:
            return Response(
                content=_feed_cache["json"],
                media_type="application/json",
            )
        elif (json_format is None and debug_format is None) and _feed_cache["protobuf"] is not None:
            return Response(
                content=_feed_cache["protobuf"],
                media_type="application/x-protobuf",
            )

    # Cache miss or expired - generate payloads with export service
    export_service = GtfsRealtimeServiceAlertsExportService(get_repository())
    protobuf_content = await export_service.export_protobuf()
    json_content = await export_service.export_json()

    # Update cache
    _feed_cache["protobuf"] = protobuf_content
    _feed_cache["json"] = json_content
    _feed_cache["timestamp"] = current_time
    
    # Return as JSON or protobuf
    # If ?json or ?debug is present (even without value), return JSON
    if json_format is not None or debug_format is not None:
        return Response(
            content=json_content,
            media_type="application/json",
        )
    else:
        return Response(
            content=protobuf_content,
            media_type="application/x-protobuf",
        )
