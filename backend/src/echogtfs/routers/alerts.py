"""
ServiceAlerts CRUD router.

Provides endpoints for managing GTFS-RT ServiceAlerts.
Create, Update, Delete require authentication.
List is public (read-only).
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from echogtfs.database import get_db
from echogtfs.models import (
    ServiceAlert,
    ServiceAlertActivePeriod,
    ServiceAlertInformedEntity,
    ServiceAlertTranslation,
    GtfsAgency,
    GtfsRoute,
    GtfsStop,
)
from echogtfs.schemas import (
    ServiceAlertCreate,
    ServiceAlertListResponse,
    ServiceAlertRead,
    ServiceAlertUpdate,
)
from echogtfs.security import CurrentUser
from echogtfs.routers.realtime import invalidate_gtfs_rt_cache

router = APIRouter()
logger = logging.getLogger("uvicorn")

_DB = Annotated[AsyncSession, Depends(get_db)]


async def _load_gtfs_entity_names(db: AsyncSession) -> dict[str, dict[str, str]]:
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
    
    # Load agencies
    result = await db.execute(select(GtfsAgency.gtfs_id, GtfsAgency.name))
    entity_names["agency"] = {row[0]: row[1] for row in result.fetchall()}
    
    # Load routes (combine short_name and long_name like the frontend does)
    result = await db.execute(select(GtfsRoute.gtfs_id, GtfsRoute.short_name, GtfsRoute.long_name))
    for gtfs_id, short_name, long_name in result.fetchall():
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
    result = await db.execute(select(GtfsStop.gtfs_id, GtfsStop.name))
    entity_names["stop"] = {row[0]: row[1] for row in result.fetchall()}
    
    return entity_names


async def _load_gtfs_entity_ids(db: AsyncSession) -> dict[str, set[str]]:
    """
    Load all GTFS entity IDs into memory for validation.
    
    Returns a dictionary mapping entity types to sets of valid IDs:
    {
        "agency": {"agency_id_1", "agency_id_2", ...},
        "route": {"route_id_1", "route_id_2", ...},
        "stop": {"stop_id_1", "stop_id_2", ...}
    }
    """
    entity_ids = {
        "agency": set(),
        "route": set(),
        "stop": set()
    }
    
    # Load agencies
    result = await db.execute(select(GtfsAgency.gtfs_id))
    entity_ids["agency"] = {row[0] for row in result.fetchall()}
    
    # Load routes
    result = await db.execute(select(GtfsRoute.gtfs_id))
    entity_ids["route"] = {row[0] for row in result.fetchall()}
    
    # Load stops
    result = await db.execute(select(GtfsStop.gtfs_id))
    entity_ids["stop"] = {row[0] for row in result.fetchall()}
    
    return entity_ids


def _validate_entity(
    entity: ServiceAlertInformedEntity, 
    entity_ids: dict[str, set[str]]
) -> bool:
    """
    Validate if an informed entity references valid GTFS entities.
    
    Args:
        entity: ServiceAlertInformedEntity to validate
        entity_ids: Dictionary of valid GTFS IDs from _load_gtfs_entity_ids()
    
    Returns:
        True if all referenced entities are valid, False otherwise
    """
    # Trip references are not managed/validated - if only trip_id is set,
    # mark the entity as invalid (trip_id without other references)
    has_trip_id = bool(entity.trip_id)
    has_agency_id = bool(entity.agency_id)
    has_route_id = bool(entity.route_id)
    has_stop_id = bool(entity.stop_id)
    
    # If only trip_id is set (without agency, route, or stop), mark as invalid
    # direction_id and route_type are just qualifiers, not primary references
    if has_trip_id and not has_agency_id and not has_route_id and not has_stop_id:
        logger.debug(
            f"Entity has only trip_id without other references - "
            f"marking as invalid (trip references not managed): trip_id={entity.trip_id}"
        )
        return False
    
    # Check each entity type that is specified
    if entity.agency_id and entity.agency_id not in entity_ids["agency"]:
        return False
    
    if entity.route_id and entity.route_id not in entity_ids["route"]:
        return False
    
    if entity.stop_id and entity.stop_id not in entity_ids["stop"]:
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
    db: _DB,
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
    # Validate and clamp parameters
    page = max(1, page)
    limit = max(1, min(100, limit))
    offset = (page - 1) * limit
    sort = sort.lower() if sort in ["newest", "oldest"] else "newest"
    search = search.strip()
    
    # Subquery to get the minimum (first) start_time for each alert
    subq = (
        select(
            ServiceAlertActivePeriod.alert_id,
            func.min(ServiceAlertActivePeriod.start_time).label('first_start')
        )
        .group_by(ServiceAlertActivePeriod.alert_id)
        .subquery()
    )
    
    # Build WHERE conditions for filters
    where_conditions = []
    if search:
        search_pattern = f"%{search}%"
        # Filter by alerts that have matching translations
        where_conditions.append(
            ServiceAlert.id.in_(
                select(ServiceAlertTranslation.alert_id)
                .where(ServiceAlertTranslation.header_text.ilike(search_pattern))
                .distinct()
            )
        )
    
    # Filter by active status
    if is_active is not None:
        where_conditions.append(ServiceAlert.is_active == is_active)
    
    # Filter by data source presence (internal vs external)
    if has_data_source is not None:
        if has_data_source:
            # External: has a data_source_id
            where_conditions.append(ServiceAlert.data_source_id.is_not(None))
        else:
            # Internal: no data_source_id
            where_conditions.append(ServiceAlert.data_source_id.is_(None))
    
    # Count total alerts (with search filter applied)
    count_stmt = select(func.count(ServiceAlert.id))
    if where_conditions:
        count_stmt = count_stmt.where(*where_conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()
    
    # Determine sort direction
    sort_expr = subq.c.first_start.desc() if sort == "newest" else subq.c.first_start.asc()
    
    # Get paginated alerts
    stmt = (
        select(ServiceAlert)
        .outerjoin(subq, ServiceAlert.id == subq.c.alert_id)
    )
    
    # Apply search filter
    if where_conditions:
        stmt = stmt.where(*where_conditions)
    
    stmt = stmt.options(
        selectinload(ServiceAlert.translations),
        selectinload(ServiceAlert.active_periods),
        selectinload(ServiceAlert.informed_entities),
        selectinload(ServiceAlert.data_source),
    ).order_by(
        # Alerts without periods first (first_start IS NULL = 0, else = 1)
        case((subq.c.first_start.is_(None), 0), else_=1),
        # Then sort by start_time
        sort_expr.nulls_last()
    ).offset(offset).limit(limit)
    
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    
    # Convert to Pydantic models first
    response = ServiceAlertListResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 1,
        items=items,
    )
    
    # Load GTFS entity names and enrich alert dicts
    entity_names = await _load_gtfs_entity_names(db)
    response_dict = response.model_dump()
    _enrich_alerts_with_entity_names(response_dict["items"], entity_names)
    
    return response_dict


@router.get("/{alert_id}", response_model=ServiceAlertRead)
async def get_alert(alert_id: UUID, db: _DB) -> ServiceAlert:
    """
    Get a single service alert by ID (public endpoint).
    """
    stmt = (
        select(ServiceAlert)
        .where(ServiceAlert.id == alert_id)
        .options(
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
            selectinload(ServiceAlert.data_source),
        )
    )
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )
    
    # Convert to Pydantic and then enrich with entity names
    alert_read = ServiceAlertRead.model_validate(alert)
    alert_dict = alert_read.model_dump()
    
    entity_names = await _load_gtfs_entity_names(db)
    _enrich_alerts_with_entity_names([alert_dict], entity_names)
    
    return alert_dict


@router.post("/", response_model=ServiceAlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: ServiceAlertCreate,
    _: CurrentUser,
    db: _DB,
) -> ServiceAlert:
    """
    Create a new service alert (requires authentication).
    """
    # Load GTFS entity IDs for validation
    entity_ids = await _load_gtfs_entity_ids(db)
    
    # Create alert
    alert = ServiceAlert(
        cause=payload.cause,
        effect=payload.effect,
        severity_level=payload.severity_level,
        is_active=payload.is_active,
    )
    db.add(alert)
    await db.flush()
    
    # Add translations
    for trans_data in payload.translations:
        translation = ServiceAlertTranslation(
            alert_id=alert.id,
            language=trans_data.language,
            header_text=trans_data.header_text,
            description_text=trans_data.description_text,
            url=trans_data.url,
        )
        db.add(translation)
    
    # Add active periods
    for period_data in payload.active_periods:
        period = ServiceAlertActivePeriod(
            alert_id=alert.id,
            start_time=period_data.start_time,
            end_time=period_data.end_time,
        )
        db.add(period)
    
    # Add informed entities with validation
    for entity_data in payload.informed_entities:
        entity = ServiceAlertInformedEntity(
            alert_id=alert.id,
            agency_id=entity_data.agency_id,
            route_id=entity_data.route_id,
            route_type=entity_data.route_type,
            stop_id=entity_data.stop_id,
            trip_id=entity_data.trip_id,
            direction_id=entity_data.direction_id,
        )
        # Validate and set is_valid flag
        entity.is_valid = _validate_entity(entity, entity_ids)
        db.add(entity)
    
    await db.commit()
    await db.refresh(alert)
    
    # Reload with relationships
    stmt = (
        select(ServiceAlert)
        .where(ServiceAlert.id == alert.id)
        .options(
            selectinload(ServiceAlert.data_source),
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
        )
    )
    result = await db.execute(stmt)
    alert = result.scalar_one()
    
    # Convert to Pydantic and then enrich with entity names
    alert_read = ServiceAlertRead.model_validate(alert)
    alert_dict = alert_read.model_dump()
    
    entity_names = await _load_gtfs_entity_names(db)
    _enrich_alerts_with_entity_names([alert_dict], entity_names)
    
    # Invalidate GTFS-RT cache since alerts changed
    invalidate_gtfs_rt_cache()
    
    return alert_dict


@router.patch("/{alert_id}", response_model=ServiceAlertRead)
async def update_alert(
    alert_id: UUID,
    payload: ServiceAlertUpdate,
    _: CurrentUser,
    db: _DB,
) -> ServiceAlert:
    """
    Update an existing service alert (requires authentication).
    Only internal alerts (data_source_id IS NULL) can be updated.
    """
    # Get existing alert
    stmt = (
        select(ServiceAlert)
        .where(ServiceAlert.id == alert_id)
        .options(
            selectinload(ServiceAlert.data_source),
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
        )
    )
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )
    
    # Check if alert is external (imported from data source)
    if alert.data_source_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit external alerts from data sources"
        )
    
    # Update basic fields
    if payload.cause is not None:
        alert.cause = payload.cause
    if payload.effect is not None:
        alert.effect = payload.effect
    if payload.severity_level is not None:
        alert.severity_level = payload.severity_level
    if payload.is_active is not None:
        alert.is_active = payload.is_active
    
    # Replace translations if provided
    if payload.translations is not None:
        # Delete existing translations
        for trans in alert.translations:
            await db.delete(trans)
        
        # Add new translations
        for trans_data in payload.translations:
            translation = ServiceAlertTranslation(
                alert_id=alert.id,
                language=trans_data.language,
                header_text=trans_data.header_text,
                description_text=trans_data.description_text,
                url=trans_data.url,
            )
            db.add(translation)
    
    # Replace active periods if provided
    if payload.active_periods is not None:
        # Delete existing periods
        for period in alert.active_periods:
            await db.delete(period)
        
        # Add new periods
        for period_data in payload.active_periods:
            period = ServiceAlertActivePeriod(
                alert_id=alert.id,
                start_time=period_data.start_time,
                end_time=period_data.end_time,
            )
            db.add(period)
    
    # Replace informed entities if provided
    if payload.informed_entities is not None:
        # Load GTFS entity IDs for validation
        entity_ids = await _load_gtfs_entity_ids(db)
        
        # Delete existing entities
        for entity in alert.informed_entities:
            await db.delete(entity)
        
        # Add new entities with validation
        for entity_data in payload.informed_entities:
            entity = ServiceAlertInformedEntity(
                alert_id=alert.id,
                agency_id=entity_data.agency_id,
                route_id=entity_data.route_id,
                route_type=entity_data.route_type,
                stop_id=entity_data.stop_id,
                trip_id=entity_data.trip_id,
                direction_id=entity_data.direction_id,
            )
            # Validate and set is_valid flag
            entity.is_valid = _validate_entity(entity, entity_ids)
            db.add(entity)
    
    await db.commit()
    await db.refresh(alert)
    
    # Reload with relationships
    stmt = (
        select(ServiceAlert)
        .where(ServiceAlert.id == alert.id)
        .options(
            selectinload(ServiceAlert.data_source),
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
        )
    )
    result = await db.execute(stmt)
    alert = result.scalar_one()
    
    # Convert to Pydantic and then enrich with entity names
    alert_read = ServiceAlertRead.model_validate(alert)
    alert_dict = alert_read.model_dump()
    
    entity_names = await _load_gtfs_entity_names(db)
    _enrich_alerts_with_entity_names([alert_dict], entity_names)
    
    # Invalidate GTFS-RT cache
    invalidate_gtfs_rt_cache()
    
    return alert_dict


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: UUID,
    _: CurrentUser,
    db: _DB,
) -> None:
    """
    Delete a service alert (requires authentication).
    Only internal alerts (data_source_id IS NULL) can be deleted.
    """
    alert = await db.get(ServiceAlert, alert_id)
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )
    
    # Check if alert is external (imported from data source)
    if alert.data_source_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete external alerts from data sources"
        )
    
    await db.delete(alert)
    await db.commit()
    
    # Invalidate GTFS-RT cache
    invalidate_gtfs_rt_cache()


@router.post("/{alert_id}/toggle-active", response_model=ServiceAlertRead)
async def toggle_alert_active(
    alert_id: UUID,
    _: CurrentUser,
    db: _DB,
) -> ServiceAlert:
    """
    Toggle the is_active flag of a service alert (requires authentication).
    This is the only operation allowed on external alerts from data sources.
    """
    # Get existing alert
    stmt = (
        select(ServiceAlert)
        .where(ServiceAlert.id == alert_id)
        .options(
            selectinload(ServiceAlert.data_source),
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
        )
    )
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )
    
    # Toggle is_active
    alert.is_active = not alert.is_active
    
    await db.commit()
    await db.refresh(alert)
    
    # Invalidate GTFS-RT cache
    invalidate_gtfs_rt_cache()
    
    # Reload with relationships
    stmt = (
        select(ServiceAlert)
        .where(ServiceAlert.id == alert.id)
        .options(
            selectinload(ServiceAlert.data_source),
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one()
