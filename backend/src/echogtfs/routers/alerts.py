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
    ServiceAlertRead,
    ServiceAlertUpdate,
)
from echogtfs.security import CurrentUser

router = APIRouter()

_DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("/", response_model=list[ServiceAlertRead])
async def list_alerts(db: _DB) -> list[ServiceAlert]:
    """
    List all service alerts (public endpoint).
    
    Returns all alerts with their translations, active periods, and informed entities.
    Alerts without periods (permanent/ongoing) appear first,
    then alerts sorted by first start_time (latest/newest first, descending).
    """
    # Subquery to get the minimum (first) start_time for each alert
    subq = (
        select(
            ServiceAlertActivePeriod.alert_id,
            func.min(ServiceAlertActivePeriod.start_time).label('first_start')
        )
        .group_by(ServiceAlertActivePeriod.alert_id)
        .subquery()
    )
    
    stmt = (
        select(ServiceAlert)
        .outerjoin(subq, ServiceAlert.id == subq.c.alert_id)
        .options(
            selectinload(ServiceAlert.translations),
            selectinload(ServiceAlert.active_periods),
            selectinload(ServiceAlert.informed_entities),
        )
        .order_by(
            # Alerts without periods first (first_start IS NULL = 0, else = 1)
            case((subq.c.first_start.is_(None), 0), else_=1),
            # Then sort by start_time descending
            subq.c.first_start.desc().nulls_last()
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


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
    return result.scalar_one()


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: UUID,
    _: CurrentUser,
    db: _DB,
) -> None:
    """
    Delete a service alert (requires authentication).
    """
    alert = await db.get(ServiceAlert, alert_id)
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )
    
    await db.delete(alert)
    await db.commit()
