"""
ServiceAlerts CRUD router.

Provides endpoints for managing GTFS-RT ServiceAlerts.
Create, Update, Delete require authentication.
List is public (read-only).
"""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from echogtfs.services.database import get_gtfs_repository, get_realtime_repository
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.validation.schemas import (
    ServiceAlertCreate,
    ServiceAlertListResponse,
    ServiceAlertRead,
    ServiceAlertUpdate,
)
from echogtfs.common.security import CurrentUser

router = APIRouter()
logger = logging.getLogger("uvicorn")

_ERR_ALERT_NOT_FOUND = "error.alert_not_found"
_ERR_CANNOT_DELETE_EXTERNAL = "error.cannot_delete_external"

_Repo = Annotated[RealtimeRepositoryInterface, Depends(get_realtime_repository)]
_GtfsRepo = Annotated[GtfsRepositoryInterface, Depends(get_gtfs_repository)]


async def _load_gtfs_entity_names(repository: GtfsRepositoryInterface) -> dict[str, dict[str, str]]:
    """
    Load all GTFS entity IDs and names into memory for fast resolution.
    
    Returns a dictionary mapping entity types to ID -> name mappings:
    {
        "agency": {"agency_id_1": "Agency Name 1", ...},
        "route": {"route_id_1": "Route Name 1", ...},
        "stop": {"stop_id_1": "Stop Name 1", ...}
    }
    """
    entity_names = {
        "agency": {},
        "route": {},
        "stop": {}
    }
    
    agencies = await repository.list_gtfs_agencies()
    entity_names["agency"] = {agency.gtfs_id: agency.name for agency in agencies}
    
    # Load routes (combine short_name and long_name like the frontend does)
    routes = await repository.list_gtfs_routes(query="", limit=100000)
    for route in routes:
        gtfs_id = route.gtfs_id
        short_name = route.short_name
        long_name = route.long_name
        # Combine names: "short - long" or fallback to whichever is available
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


async def _load_gtfs_entity_ids(repository: GtfsRepositoryInterface) -> dict[str, set[str]]:
    """
    Load all GTFS entity IDs into memory for validation.
    
    Returns a dictionary mapping entity types to sets of valid IDs:
    {
        "agency": {"agency_id_1", "agency_id_2", ...},
        "route": {"route_id_1", "route_id_2", ...},
        "stop": {"stop_id_1", "stop_id_2", ...}
    }
    """
    return await repository.list_gtfs_entity_ids()


def _validate_entity(
    entity: dict[str, Any],
    entity_ids: dict[str, set[str]]
) -> bool:
    """
    Validate if an informed entity references valid GTFS entities.
    
    Args:
        entity: Informed entity payload to validate
        entity_ids: Dictionary of valid GTFS IDs from _load_gtfs_entity_ids()
    
    Returns:
        True if all referenced entities are valid, False otherwise
    """
    # Trip references are not managed/validated - if only trip_id is set,
    # mark the entity as invalid (trip_id without other references)
    has_trip_id = bool(entity.get("trip_id"))
    has_agency_id = bool(entity.get("agency_id"))
    has_route_id = bool(entity.get("route_id"))
    has_stop_id = bool(entity.get("stop_id"))
    
    # If only trip_id is set (without agency, route, or stop), mark as invalid
    # direction_id and route_type are just qualifiers, not primary references
    if has_trip_id and not has_agency_id and not has_route_id and not has_stop_id:
        logger.debug(
            f"Entity has only trip_id without other references - "
            f"marking as invalid (trip references not managed): trip_id={entity.get('trip_id')}"
        )
        return False
    
    # Check each entity type that is specified
    if entity.get("agency_id") and entity["agency_id"] not in entity_ids["agency"]:
        return False
    
    if entity.get("route_id") and entity["route_id"] not in entity_ids["route"]:
        return False
    
    if entity.get("stop_id") and entity["stop_id"] not in entity_ids["stop"]:
        return False
    
    return True


def _enrich_alerts_with_entity_names(
    alerts: list[dict], 
    entity_names: dict[str, dict[str, str]]
) -> None:
    """
    Enrich alert dicts with resolved GTFS entity names.
    Modifies the alert dicts in-place by adding name fields to informed entities.
    
    Args:
        alerts: List of alert dicts (already serialized from Pydantic)
        entity_names: Dictionary from _load_gtfs_entity_names()
    """
    for alert in alerts:
        for entity in alert.get("informed_entities", []):
            # Resolve agency name
            if entity.get("agency_id"):
                entity["agency_name"] = entity_names["agency"].get(entity["agency_id"])
            
            # Resolve route name
            if entity.get("route_id"):
                entity["route_name"] = entity_names["route"].get(entity["route_id"])
            
            # Resolve stop name
            if entity.get("stop_id"):
                entity["stop_name"] = entity_names["stop"].get(entity["stop_id"])


@router.get("/", response_model=ServiceAlertListResponse)
async def list_alerts(
    repository: _Repo,
    gtfs_repository: _GtfsRepo,
    page: int = 1,
    limit: int = 20,
    sort: str = "newest",
    search: str = "",
    is_active: bool | None = None,
    has_data_source: bool | None = None,
) -> ServiceAlertListResponse:
    """
    List service alerts with pagination (public endpoint).
    
    Returns alerts with their translations, active periods, and informed entities.
    Alerts without periods (permanent/ongoing) appear first,
    then alerts sorted by first start_time.
    
    Query parameters:
    - page: Page number (1-indexed, default: 1)
    - limit: Items per page (default: 20, max: 100)
    - sort: Sort order - "newest" (default) or "oldest"
    - search: Search filter (searches in header_text of translations)
    - is_active: Filter by active status (true/false, optional)
    - has_data_source: Filter by data source presence - true = external, false = internal (optional)
    """
    page = max(1, page)
    limit = max(1, min(100, limit))
    sort = sort.lower() if sort in ["newest", "oldest"] else "newest"
    search = search.strip()
    items, total = await repository.list_service_alerts_paginated(
        page=page,
        limit=limit,
        sort=sort,
        search=search,
        is_active=is_active,
        has_data_source=has_data_source,
    )
    
    # Convert to Pydantic models first
    response = ServiceAlertListResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 1,
        items=items,
    )
    
    # Load GTFS entity names and enrich alert dicts
    entity_names = await _load_gtfs_entity_names(gtfs_repository)
    response_dict = response.model_dump()
    _enrich_alerts_with_entity_names(response_dict["items"], entity_names)
    
    return response_dict


@router.get("/{alert_id}", response_model=ServiceAlertRead)
async def get_alert(alert_id: UUID, repository: _Repo, gtfs_repository: _GtfsRepo) -> ServiceAlertRead:
    """
    Get a single service alert by ID (public endpoint).
    """
    alert = await repository.get_service_alert_by_id_with_relations(alert_id)
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_ERR_ALERT_NOT_FOUND,
        )
    
    # Convert to Pydantic and then enrich with entity names
    alert_read = ServiceAlertRead.model_validate(alert)
    alert_dict = alert_read.model_dump()
    
    entity_names = await _load_gtfs_entity_names(gtfs_repository)
    _enrich_alerts_with_entity_names([alert_dict], entity_names)
    
    return alert_dict


@router.post("/", response_model=ServiceAlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: ServiceAlertCreate,
    _: CurrentUser,
    repository: _Repo,
    gtfs_repository: _GtfsRepo,
) -> ServiceAlertRead:
    """
    Create a new service alert (requires authentication).
    """
    # Load GTFS entity IDs for validation
    entity_ids = await _load_gtfs_entity_ids(gtfs_repository)

    informed_entities = []
    for entity_data in payload.informed_entities:
        entity_payload = {
            "agency_id": entity_data.agency_id,
            "route_id": entity_data.route_id,
            "route_type": entity_data.route_type,
            "stop_id": entity_data.stop_id,
            "trip_id": entity_data.trip_id,
            "direction_id": entity_data.direction_id,
        }
        entity_payload["is_valid"] = _validate_entity(entity_payload, entity_ids)
        informed_entities.append(entity_payload)

    alert = await repository.create_service_alert(
        cause=payload.cause,
        effect=payload.effect,
        severity_level=payload.severity_level,
        is_active=payload.is_active,
        translations=[
            {
                "language": trans_data.language,
                "header_text": trans_data.header_text,
                "description_text": trans_data.description_text,
                "url": trans_data.url,
            }
            for trans_data in payload.translations
        ],
        active_periods=[
            {
                "period_type": period_data.period_type,
                "start_time": period_data.start_time,
                "end_time": period_data.end_time,
            }
            for period_data in payload.active_periods
        ],
        informed_entities=informed_entities,
    )
    
    # Convert to Pydantic and then enrich with entity names
    alert_read = ServiceAlertRead.model_validate(alert)
    alert_dict = alert_read.model_dump()
    
    entity_names = await _load_gtfs_entity_names(gtfs_repository)
    _enrich_alerts_with_entity_names([alert_dict], entity_names)
    
    return alert_dict


@router.post("/{alert_id}/toggle-active", response_model=ServiceAlertRead)
async def toggle_alert_active(
    alert_id: UUID,
    _: CurrentUser,
    repository: _Repo,
) -> ServiceAlertRead:
    """
    Toggle the is_active flag of a service alert (requires authentication).
    This is the only operation allowed on external alerts from data sources.
    """
    alert = await repository.toggle_service_alert_active(alert_id)
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_ERR_ALERT_NOT_FOUND,
        )
    
    return alert


@router.patch("/{alert_id}", response_model=ServiceAlertRead)
async def update_alert(
    alert_id: UUID,
    payload: ServiceAlertUpdate,
    _: CurrentUser,
    repository: _Repo,
    gtfs_repository: _GtfsRepo,
) -> ServiceAlertRead:
    """
    Update an existing service alert (requires authentication).
    Only internal alerts (data_source_id IS NULL) can be updated.
    """
    # Get existing alert
    alert = await repository.get_service_alert_by_id_with_relations(alert_id)
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_ERR_ALERT_NOT_FOUND,
        )
    
    # Check if alert is external (imported from data source)
    if alert.data_source_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit external alerts from data sources"
        )
    
    translations_data = None
    if payload.translations is not None:
        translations_data = [
            {
                "language": trans_data.language,
                "header_text": trans_data.header_text,
                "description_text": trans_data.description_text,
                "url": trans_data.url,
            }
            for trans_data in payload.translations
        ]

    active_periods_data = None
    if payload.active_periods is not None:
        active_periods_data = [
            {
                "period_type": period_data.period_type,
                "start_time": period_data.start_time,
                "end_time": period_data.end_time,
            }
            for period_data in payload.active_periods
        ]

    informed_entities_data = None
    if payload.informed_entities is not None:
        entity_ids = await _load_gtfs_entity_ids(gtfs_repository)
        informed_entities_data = []
        for entity_data in payload.informed_entities:
            entity_payload = {
                "agency_id": entity_data.agency_id,
                "route_id": entity_data.route_id,
                "route_type": entity_data.route_type,
                "stop_id": entity_data.stop_id,
                "trip_id": entity_data.trip_id,
                "direction_id": entity_data.direction_id,
            }
            entity_payload["is_valid"] = _validate_entity(entity_payload, entity_ids)
            informed_entities_data.append(entity_payload)

    alert = await repository.update_service_alert(
        alert_id,
        cause=payload.cause,
        effect=payload.effect,
        severity_level=payload.severity_level,
        is_active=payload.is_active,
        translations=translations_data,
        active_periods=active_periods_data,
        informed_entities=informed_entities_data,
    )

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_ERR_ALERT_NOT_FOUND,
        )
    
    # Convert to Pydantic and then enrich with entity names
    alert_read = ServiceAlertRead.model_validate(alert)
    alert_dict = alert_read.model_dump()
    
    entity_names = await _load_gtfs_entity_names(gtfs_repository)
    _enrich_alerts_with_entity_names([alert_dict], entity_names)
    
    return alert_dict


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: UUID,
    _: CurrentUser,
    repository: _Repo,
) -> None:
    """
    Delete a service alert (requires authentication).
    Only internal alerts (data_source_id IS NULL) can be deleted.
    """
    alert = await repository.get_service_alert_by_id_with_relations(alert_id)
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_ERR_ALERT_NOT_FOUND,
        )
    
    # Check if alert is external (imported from data source)
    if alert.data_source_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_ERR_CANNOT_DELETE_EXTERNAL,
        )
    
    await repository.delete_service_alerts_by_ids([alert_id])
