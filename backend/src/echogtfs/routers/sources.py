"""
Data sources router
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from echogtfs.database import get_db
from echogtfs.models import DataSource, DataSourceMapping, User
from echogtfs.schemas import DataSourceCreate, DataSourceRead, DataSourceUpdate
from echogtfs.security import CurrentPoweruser
from echogtfs.services.adapters import ADAPTER_REGISTRY
from echogtfs.services.alert_import import schedule_data_source_import, run_import_task

router = APIRouter()


@router.get("/adapter-types")
async def list_adapter_types(current_user: CurrentPoweruser):
    """
    List all available adapter types with their configuration schemas.
    Requires poweruser or admin role.
    
    Returns:
        List of adapter type definitions with config field schemas
    """
    adapter_types = []
    for adapter_name, adapter_class in ADAPTER_REGISTRY.items():
        adapter_types.append({
            "type": adapter_name,
            "config_schema": adapter_class.get_config_schema(),
        })
    
    return {"adapter_types": adapter_types}


@router.get("/", response_model=List[DataSourceRead])
async def list_sources(
    current_user: CurrentPoweruser,
    db: AsyncSession = Depends(get_db),
):
    """
    List all data sources with their mappings.
    Requires poweruser or admin role.
    """
    result = await db.execute(
        select(DataSource)
        .options(selectinload(DataSource.mappings))
        .order_by(DataSource.name)
    )
    sources = result.scalars().all()
    return sources


@router.post("/", response_model=DataSourceRead, status_code=201)
async def create_source(
    source_data: DataSourceCreate,
    current_user: CurrentPoweruser,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new data source with mappings.
    Requires poweruser or admin role.
    """
    # Check if name already exists
    result = await db.execute(
        select(DataSource).where(DataSource.name == source_data.name)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Data source with this name already exists")
    
    # Create data source
    source = DataSource(
        name=source_data.name,
        type=source_data.type,
        config=source_data.config,
        cron=source_data.cron,
    )
    db.add(source)
    await db.flush()  # Get the ID
    
    # Create mappings
    for mapping_data in source_data.mappings:
        mapping = DataSourceMapping(
            data_source_id=source.id,
            entity_type=mapping_data.entity_type,
            key=mapping_data.key,
            value=mapping_data.value,
        )
        db.add(mapping)
    
    await db.commit()
    await db.refresh(source)
    
    # Schedule cron job if cron expression is set
    if source.cron:
        await schedule_data_source_import(source.id, source.name, source.cron)
    
    # Load relationships
    result = await db.execute(
        select(DataSource)
        .where(DataSource.id == source.id)
        .options(selectinload(DataSource.mappings))
    )
    source = result.scalar_one()
    
    return source


@router.get("/{source_id}", response_model=DataSourceRead)
async def get_source(
    source_id: int,
    current_user: CurrentPoweruser,
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single data source by ID with mappings.
    Requires poweruser or admin role.
    """
    result = await db.execute(
        select(DataSource)
        .where(DataSource.id == source_id)
        .options(selectinload(DataSource.mappings))
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    return source


@router.patch("/{source_id}", response_model=DataSourceRead)
async def update_source(
    source_id: int,
    source_data: DataSourceUpdate,
    current_user: CurrentPoweruser,
    db: AsyncSession = Depends(get_db),
):
    """
    Update a data source and optionally replace its mappings.
    Requires poweruser or admin role.
    """
    result = await db.execute(
        select(DataSource)
        .where(DataSource.id == source_id)
        .options(selectinload(DataSource.mappings))
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # Update basic fields
    old_name = source.name
    if source_data.name is not None:
        # Check if new name conflicts with another source
        name_result = await db.execute(
            select(DataSource).where(
                DataSource.name == source_data.name,
                DataSource.id != source_id
            )
        )
        if name_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Data source with this name already exists")
        source.name = source_data.name
        
        # Update all alerts from this source to use the new name
        from sqlalchemy import update
        from echogtfs.models import ServiceAlert
        await db.execute(
            update(ServiceAlert)
            .where(ServiceAlert.source == old_name)
            .values(source=source_data.name)
        )
    
    if source_data.type is not None:
        source.type = source_data.type
    
    if source_data.config is not None:
        source.config = source_data.config
    
    if source_data.cron is not None:
        source.cron = source_data.cron
    
    # Replace mappings if provided
    if source_data.mappings is not None:
        # Delete existing mappings
        await db.execute(
            select(DataSourceMapping)
            .where(DataSourceMapping.data_source_id == source_id)
        )
        for mapping in source.mappings:
            await db.delete(mapping)
        
        # Create new mappings
        for mapping_data in source_data.mappings:
            mapping = DataSourceMapping(
                data_source_id=source.id,
                entity_type=mapping_data.entity_type,
                key=mapping_data.key,
                value=mapping_data.value,
            )
            db.add(mapping)
    
    await db.commit()
    
    # Update cron job
    await schedule_data_source_import(source.id, source.name, source.cron)
    
    # Reload with relationships
    result = await db.execute(
        select(DataSource)
        .where(DataSource.id == source_id)
        .options(selectinload(DataSource.mappings))
    )
    source = result.scalar_one()
    
    return source


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: int,
    current_user: CurrentPoweruser,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a data source (cascades to mappings).
    Requires poweruser or admin role.
    """
    result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # Remove cron job if exists
    await schedule_data_source_import(source.id, source.name, None)
    
    await db.delete(source)
    await db.commit()


@router.post("/{source_id}/run", status_code=202)
async def run_source_import(
    source_id: int,
    current_user: CurrentPoweruser,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger an import for a specific data source.
    Requires poweruser or admin role.
    
    Returns:
        Accepted response - import runs in background
    """
    # Check if source exists
    result = await db.execute(
        select(DataSource).where(DataSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # Trigger import task asynchronously
    import asyncio
    asyncio.create_task(run_import_task(source_id))
    
    return {"message": f"Import for data source '{source.name}' has been triggered"}
