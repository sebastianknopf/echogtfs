"""
ServiceAlerts CRUD router.

Provides endpoints for managing GTFS-RT ServiceAlerts.
Create, Update, Delete require authentication.
List is public (read-only).
"""

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

_DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("/", response_model=ServiceAlertListResponse)
async def list_alerts(
    db: _DB,
    page: int = 1,
    limit: int = 20,
    sort: str = "newest",
    search: str = "",
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
    
    # Build WHERE conditions for search filter
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
    ).order_by(
        # Alerts without periods first (first_start IS NULL = 0, else = 1)
        case((subq.c.first_start.is_(None), 0), else_=1),
        # Then sort by start_time
        sort_expr.nulls_last()
    ).offset(offset).limit(limit)
    
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    
    total_pages = (total + limit - 1) // limit if total > 0 else 1
    
    return ServiceAlertListResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        items=items,
    )


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
        )
    )
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )
    
    return alert


@router.post("/", response_model=ServiceAlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: ServiceAlertCreate,
    _: CurrentUser,
    db: _DB,
) -> ServiceAlert:
    """
    Create a new service alert (requires authentication).
    """
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
    
    # Add informed entities
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
        db.add(entity)
    
    await db.commit()
    await db.refresh(alert)
    
    # Reload with relationships
    stmt = (
        select(ServiceAlert)
        .where(ServiceAlert.id == alert.id)
        .options(
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one()


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
        # Delete existing entities
        for entity in alert.informed_entities:
            await db.delete(entity)
        
        # Add new entities
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
            db.add(entity)
    
    await db.commit()
    await db.refresh(alert)
    
    # Reload with relationships
    stmt = (
        select(ServiceAlert)
        .where(ServiceAlert.id == alert.id)
        .options(
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
        )
    )
    result = await db.execute(stmt)
    
    # Invalidate GTFS-RT cache
    invalidate_gtfs_rt_cache()
    
    return result.scalar_one()


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
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one()
