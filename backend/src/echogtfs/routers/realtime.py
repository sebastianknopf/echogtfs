"""
GTFS-Realtime ServiceAlerts endpoint.

Exports service alerts as GTFS-RT protobuf or JSON format.
This endpoint is public by default, but can be protected via Basic Auth
if credentials are configured in settings.
"""

import base64
import json
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from echogtfs import gtfs_realtime_pb2
from echogtfs.database import get_db
from echogtfs.models import ServiceAlert
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


def _build_feed_message(alerts: list[ServiceAlert]) -> gtfs_realtime_pb2.FeedMessage:
    """
    Build a GTFS-RT FeedMessage from ServiceAlert models.
    
    Args:
        alerts: List of ServiceAlert instances with loaded relationships
        
    Returns:
        gtfs_realtime_pb2.FeedMessage ready for serialization
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    
    # Header
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET
    feed.header.timestamp = int(time.time())
    
    # Process alerts (already filtered for active in query)
    for alert_model in alerts:
            
        entity = feed.entity.add()
        entity.id = str(alert_model.id)
        
        alert = entity.alert
        
        # Cause and effect (stored as strings in DB)
        if alert_model.cause:
            alert.cause = getattr(
                gtfs_realtime_pb2.Alert.Cause, 
                alert_model.cause,  # Already a string like "TECHNICAL_PROBLEM"
                gtfs_realtime_pb2.Alert.Cause.UNKNOWN_CAUSE
            )
        
        if alert_model.effect:
            alert.effect = getattr(
                gtfs_realtime_pb2.Alert.Effect,
                alert_model.effect,  # Already a string like "REDUCED_SERVICE"
                gtfs_realtime_pb2.Alert.Effect.UNKNOWN_EFFECT
            )
        
        # Severity level (GTFS-RT SeverityLevel enum)
        if alert_model.severity_level:
            severity_map = {
                "UNKNOWN_SEVERITY": gtfs_realtime_pb2.Alert.UNKNOWN_SEVERITY,
                "INFO": gtfs_realtime_pb2.Alert.INFO,
                "WARNING": gtfs_realtime_pb2.Alert.WARNING,
                "SEVERE": gtfs_realtime_pb2.Alert.SEVERE,
            }
            alert.severity_level = severity_map.get(
                alert_model.severity_level,
                gtfs_realtime_pb2.Alert.UNKNOWN_SEVERITY
            )
        
        # Translations (header and description)
        for trans in alert_model.translations:
            if trans.header_text:
                header = alert.header_text.translation.add()
                header.text = trans.header_text
                header.language = trans.language
            
            if trans.description_text:
                desc = alert.description_text.translation.add()
                desc.text = trans.description_text
                desc.language = trans.language
            
            if trans.url:
                url = alert.url.translation.add()
                url.text = trans.url
                url.language = trans.language
        
        # Active periods
        for period in alert_model.active_periods:
            time_range = alert.active_period.add()
            if period.start_time is not None:
                time_range.start = period.start_time
            if period.end_time is not None:
                time_range.end = period.end_time
        
        # Informed entities
        for entity_model in alert_model.informed_entities:
            informed = alert.informed_entity.add()
            
            if entity_model.agency_id:
                informed.agency_id = entity_model.agency_id
            if entity_model.route_id:
                informed.route_id = entity_model.route_id
            if entity_model.route_type is not None:
                informed.route_type = entity_model.route_type
            if entity_model.stop_id:
                informed.stop_id = entity_model.stop_id
            if entity_model.direction_id is not None:
                informed.direction_id = entity_model.direction_id
            
            # Only create TripDescriptor if trip_id is present
            if entity_model.trip_id:
                informed.trip.trip_id = entity_model.trip_id
    
    return feed


def _feed_to_dict(feed: gtfs_realtime_pb2.FeedMessage) -> dict:
    """
    Convert GTFS-RT FeedMessage to a JSON-serializable dictionary.
    
    Args:
        feed: gtfs_realtime_pb2.FeedMessage
        
    Returns:
        Dictionary representation of the feed
    """
    result = {
        "header": {
            "gtfs_realtime_version": feed.header.gtfs_realtime_version,
            "incrementality": gtfs_realtime_pb2.FeedHeader.Incrementality.Name(
                feed.header.incrementality
            ),
            "timestamp": feed.header.timestamp,
        },
        "entity": [],
    }
    
    for entity in feed.entity:
        entity_dict = {"id": entity.id}
        
        if entity.HasField("alert"):
            alert = entity.alert
            alert_dict = {}
            
            # Cause and effect
            if alert.HasField("cause"):
                alert_dict["cause"] = gtfs_realtime_pb2.Alert.Cause.Name(alert.cause)
            if alert.HasField("effect"):
                alert_dict["effect"] = gtfs_realtime_pb2.Alert.Effect.Name(alert.effect)
            
            # Severity level
            if alert.HasField("severity_level"):
                severity_names = {
                    gtfs_realtime_pb2.Alert.UNKNOWN_SEVERITY: "UNKNOWN_SEVERITY",
                    gtfs_realtime_pb2.Alert.INFO: "INFO",
                    gtfs_realtime_pb2.Alert.WARNING: "WARNING",
                    gtfs_realtime_pb2.Alert.SEVERE: "SEVERE",
                }
                alert_dict["severity_level"] = severity_names.get(
                    alert.severity_level, "UNKNOWN_SEVERITY"
                )
            
            # Translations
            if alert.header_text.translation:
                alert_dict["header_text"] = {
                    "translation": [
                        {"text": t.text, "language": t.language}
                        for t in alert.header_text.translation
                    ]
                }
            
            if alert.description_text.translation:
                alert_dict["description_text"] = {
                    "translation": [
                        {"text": t.text, "language": t.language}
                        for t in alert.description_text.translation
                    ]
                }
            
            if alert.url.translation:
                alert_dict["url"] = {
                    "translation": [
                        {"text": t.text, "language": t.language}
                        for t in alert.url.translation
                    ]
                }
            
            # Active periods
            if alert.active_period:
                alert_dict["active_period"] = []
                for period in alert.active_period:
                    period_dict = {}
                    if period.HasField("start"):
                        period_dict["start"] = period.start
                    if period.HasField("end"):
                        period_dict["end"] = period.end
                    alert_dict["active_period"].append(period_dict)
            
            # Informed entities
            if alert.informed_entity:
                alert_dict["informed_entity"] = []
                for informed in alert.informed_entity:
                    informed_dict = {}
                    if informed.HasField("agency_id"):
                        informed_dict["agency_id"] = informed.agency_id
                    if informed.HasField("route_id"):
                        informed_dict["route_id"] = informed.route_id
                    if informed.HasField("route_type"):
                        informed_dict["route_type"] = informed.route_type
                    if informed.HasField("stop_id"):
                        informed_dict["stop_id"] = informed.stop_id
                    if informed.HasField("direction_id"):
                        informed_dict["direction_id"] = informed.direction_id
                    if informed.HasField("trip"):
                        trip_dict = {}
                        if informed.trip.HasField("trip_id"):
                            trip_dict["trip_id"] = informed.trip.trip_id
                        if informed.trip.HasField("route_id"):
                            trip_dict["route_id"] = informed.trip.route_id
                        if informed.trip.HasField("direction_id"):
                            trip_dict["direction_id"] = informed.trip.direction_id
                        if trip_dict:
                            informed_dict["trip"] = trip_dict
                    alert_dict["informed_entity"].append(informed_dict)
            
            entity_dict["alert"] = alert_dict
        
        result["entity"].append(entity_dict)
    
    return result


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
    
    # Cache miss or expired - load from database
    # Load only active alerts with their relationships
    stmt = (
        select(ServiceAlert)
        .where(ServiceAlert.is_active == True)
        .options(
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
        )
        .order_by(ServiceAlert.id)
    )
    
    result = await db.execute(stmt)
    alerts = list(result.scalars().all())
    
    # Build GTFS-RT feed
    feed = _build_feed_message(alerts)
    
    # Generate both formats and cache them
    protobuf_content = feed.SerializeToString()
    json_content = json.dumps(_feed_to_dict(feed), indent=2).encode("utf-8")
    
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
