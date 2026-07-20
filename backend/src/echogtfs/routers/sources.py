"""
Data sources router
"""
import asyncio
import logging
import os
import tempfile
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse

from echogtfs.services.database import SystemRepositoryInterface, get_system_repository
from echogtfs.services.database.models import DataSource
from echogtfs.services.scheduler import get_datasource_scheduler_service
from echogtfs.validation.schemas import DataSourceCreate, DataSourceRead, DataSourceUpdate, DataSourceLogRead
from echogtfs.common.security import CurrentPoweruser
from echogtfs.datasources import DATASOURCE_REGISTRY
from echogtfs.services.datalog import DatalogService
from echogtfs.services.mapping import MappingExportService, MappingImportService, MappingServiceError

router = APIRouter()
logger = logging.getLogger("uvicorn")

_Repo = Annotated[SystemRepositoryInterface, Depends(get_system_repository)]


async def _enrich_source_with_error_flag(source: DataSource, repository: SystemRepositoryInterface) -> DataSourceRead:
    """
    Convert a DataSource model to DataSourceRead schema with error flag.
    
    Checks the most recent log entry for this data source and sets has_error=True
    if the status code is in the 4xx or 5xx range.
    
    Args:
        source: DataSource model instance
        repository: Repository abstraction
    
    Returns:
        DataSourceRead schema with has_error flag set
    """
    # Get the most recent log entry
    last_log = await repository.get_latest_data_source_log(source.id)
    
    # Determine if there's an error based on HTTP status code
    has_error = False
    if last_log and last_log.status_code:
        # 4xx and 5xx status codes indicate errors
        has_error = last_log.status_code >= 400
    
    # Convert to schema
    source_dict = {
        "id": source.id,
        "name": source.name,
        "type": source.type,
        "config": source.config,
        "cron": source.cron,
        "is_active": source.is_active,
        "invalid_reference_policy": source.invalid_reference_policy,
        "last_run_at": source.last_run_at,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
        "mappings": source.mappings,
        "enrichments": source.enrichments,
        "has_error": has_error,
    }
    
    return DataSourceRead.model_validate(source_dict)


@router.get("/adapter-types")
async def list_adapter_types(_: CurrentPoweruser):
    """
    List all available adapter types with their configuration schemas.
    Requires poweruser or admin role.
    
    Returns:
        List of adapter type definitions with config field schemas
    """
    adapter_types = []
    for adapter_name, adapter_class in DATASOURCE_REGISTRY.items():
        adapter_types.append({
            "type": adapter_name,
            "config_schema": adapter_class.get_config_schema(),
        })
    
    return {"adapter_types": adapter_types}


@router.get("/", response_model=List[DataSourceRead])
async def list_sources(
    _: CurrentPoweruser,
    repository: _Repo,
):
    """
    List all data sources with their mappings and enrichments.
    Requires poweruser or admin role.
    """
    sources = await repository.list_data_sources()
    
    # Enrich each source with error flag
    enriched_sources = []
    for source in sources:
        enriched = await _enrich_source_with_error_flag(source, repository)
        enriched_sources.append(enriched)
    
    return enriched_sources


@router.get("/{source_id}", response_model=DataSourceRead)
async def get_source(
    source_id: int,
    _: CurrentPoweruser,
    repository: _Repo,
):
    """
    Get a single data source by ID with mappings and enrichments.
    Requires poweruser or admin role.
    """
    source = await repository.get_data_source_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    return await _enrich_source_with_error_flag(source, repository)


@router.get("/{source_id}/mappings/{entity_type}/export")
async def export_mappings_csv(
    source_id: int,
    entity_type: str,
    _: CurrentPoweruser,
    repository: _Repo,
):
    """
    Export mappings for a specific data source and entity type as CSV.
    Requires poweruser or admin role.
    
    Returns:
        CSV file with key;value format (no header, semicolon-separated, UTF-8 encoded)
    """
    export_service = MappingExportService()
    try:
        csv_stream = await export_service.export_csv_stream(repository, source_id, entity_type)
    except MappingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    # Create filename
    filename = f"mappings-{source_id}-{entity_type}.csv"
    
    # Return as streaming response with UTF-8 encoding
    return StreamingResponse(
        csv_stream,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/{source_id}/logs", response_model=List[DataSourceLogRead])
async def list_source_logs(
    source_id: int,
    _: CurrentPoweruser,
    repository: _Repo,
    limit: int = 100,
):
    """
    List recent log entries for a specific data source.
    Requires poweruser or admin role.
    
    Args:
        source_id: ID of the data source
        limit: Maximum number of log entries to return (default: 100, max: 1000)
    
    Returns:
        List of log entries, ordered by timestamp descending (newest first)
    """
    # Validate limit
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 1000")
    
    # Check if source exists
    if await repository.get_data_source_by_id(source_id) is None:
        raise HTTPException(status_code=404, detail="Data source not found")

    logs = await repository.list_data_source_logs(source_id, limit=limit)
    
    return logs


@router.get("/logs/{log_id}/download")
async def download_log_file(
    log_id: int,
    background_tasks: BackgroundTasks,
    _: CurrentPoweruser,
    repository: _Repo,
):
    """
    Download the log file for a specific log entry.
    Requires poweruser or admin role.
    
    The file extension and content type are determined by the log's MIME type:
    - application/json -> .json
    - application/xml -> .xml
    - text/plain -> .txt
    - Other types -> .log
    
    Args:
        log_id: ID of the log entry
    
    Returns:
        File download response with appropriate content type
    """
    # Get log entry
    log_entry = await repository.get_data_source_log_by_id(log_id)
    
    if not log_entry:
        raise HTTPException(status_code=404, detail="Log entry not found")
    
    # Get log file content
    log_content = await DatalogService(repository).get_log_content(log_entry.log_file_uuid)
    
    if log_content is None:
        raise HTTPException(status_code=404, detail="Log file not found on disk")
    
    # Determine file extension and media type based on MIME type
    mime_type = log_entry.response_mimetype or "text/plain"
    
    if mime_type == "application/json":
        extension = "json"
        media_type = "application/json"
    elif mime_type == "application/xml":
        extension = "xml"
        media_type = "application/xml"
    elif mime_type.startswith("text/"):
        extension = "txt"
        media_type = "text/plain"
    else:
        extension = "log"
        media_type = "application/octet-stream"
    
    # Create filename: log_{log_id}_{timestamp}.{extension}
    timestamp = log_entry.timestamp.strftime("%Y%m%d_%H%M%S")
    filename = f"log_{log_id}_{timestamp}.{extension}"
    
    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix=f".{extension}")
    temp_file.write(log_content)
    temp_file.close()
    temp_path = temp_file.name
    
    # Add background task to delete temporary file after response is sent
    background_tasks.add_task(os.unlink, temp_path)
    
    # Return file response with proper headers
    return FileResponse(
        path=temp_path,
        media_type=media_type,
        filename=filename,
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.post("/", response_model=DataSourceRead, status_code=201)
async def create_source(
    source_data: DataSourceCreate,
    _: CurrentPoweruser,
    repository: _Repo,
):
    """
    Create a new data source with mappings and enrichments.
    Requires poweruser or admin role.
    """
    # Check if name already exists
    if await repository.data_source_name_exists(source_data.name):
        raise HTTPException(status_code=400, detail="Data source with this name already exists")

    source = await repository.create_data_source(
        name=source_data.name,
        source_type=source_data.type,
        config=source_data.config,
        cron=source_data.cron,
        is_active=source_data.is_active,
        invalid_reference_policy=source_data.invalid_reference_policy,
        mappings=[
            {
                "entity_type": mapping_data.entity_type,
                "key": mapping_data.key,
                "value": mapping_data.value,
            }
            for mapping_data in source_data.mappings
        ],
        enrichments=[
            {
                "enrichment_type": enrichment_data.enrichment_type,
                "source_field": enrichment_data.source_field,
                "key": enrichment_data.key,
                "value": enrichment_data.value,
                "sort_order": enrichment_data.sort_order,
            }
            for enrichment_data in source_data.enrichments
        ],
    )
    
    # Schedule cron job if active and cron expression is set
    if source.is_active and source.cron:
        await get_datasource_scheduler_service().schedule_data_source_import(source.id, source.name, source.cron)
    
    return await _enrich_source_with_error_flag(source, repository)


@router.post("/{source_id}/run", status_code=202)
async def run_source_import(
    source_id: int,
    _: CurrentPoweruser,
    repository: _Repo,
):
    """
    Manually trigger an import for a specific data source.
    Requires poweruser or admin role.
    
    Returns:
        Accepted response - import runs in background
    """
    # Check if source exists
    source = await repository.get_data_source_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    # Trigger import task asynchronously
    asyncio.create_task(get_datasource_scheduler_service().run_import_task(source_id))
    
    return {"message": f"Import for data source '{source.name}' has been triggered"}


@router.post("/{source_id}/toggle-active", response_model=DataSourceRead)
async def toggle_source_active(
    source_id: int,
    _: CurrentPoweruser,
    repository: _Repo,
) -> DataSourceRead:
    """
    Toggle the is_active flag of a data source (requires poweruser/admin).
    When deactivating, all alerts from this source will be deleted.
    
    Returns:
        Updated data source
    """
    source = await repository.get_data_source_by_id(source_id)
    
    if not source:
        raise HTTPException(
            status_code=404,
            detail="Data source not found"
        )
    
    old_status = source.is_active
    source = await repository.toggle_data_source_active(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # If deactivating, delete all alerts from this source
    if old_status and not source.is_active:
        deleted_count = await repository.delete_alerts_for_data_source(source_id)

        logger.info(
            f"Deactivated data source {source_id} '{source.name}': "
            f"Deleted {deleted_count} associated alerts"
        )
    
    # Update cron job: remove if deactivated, add if activated
    if source.is_active and source.cron:
        # Re-schedule the cron job when activating
        await get_datasource_scheduler_service().schedule_data_source_import(source.id, source.name, source.cron)
    elif not source.is_active:
        # Remove the cron job when deactivating
        await get_datasource_scheduler_service().schedule_data_source_import(source.id, source.name, None)
    
    source = await repository.get_data_source_by_id(source.id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")

    return await _enrich_source_with_error_flag(source, repository)


@router.post("/{source_id}/mappings/{entity_type}/import")
async def import_mappings_csv(
    source_id: int,
    entity_type: str,
    _: CurrentPoweruser,
    repository: _Repo,
    file: UploadFile = File(...),
):
    """
    Import mappings for a specific data source and entity type from CSV.
    Requires poweruser or admin role.
    
    This is a full dump import - all existing mappings for this entity type
    will be deleted and replaced with the uploaded data.
    
    Expected format: key;value (semicolon-separated, no header, UTF-8 encoded)
    
    Args:
        source_id: ID of the data source
        entity_type: Type of entity (agency, route, stop, etc.)
        file: CSV file upload
        
    Returns:
        Success message with count of imported mappings
    """
    import_service = MappingImportService()
    try:
        inserted_count = await import_service.import_csv_stream(
            repository=repository,
            source_id=source_id,
            entity_type=entity_type,
            stream=file.file,
            filename=file.filename,
        )
    except MappingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    
    return {
        "message": f"Successfully imported {inserted_count} mappings",
        "count": inserted_count,
        "entity_type": entity_type
    }


@router.patch("/{source_id}", response_model=DataSourceRead)
async def update_source(
    source_id: int,
    source_data: DataSourceUpdate,
    _: CurrentPoweruser,
    repository: _Repo,
):
    """
    Update a data source and optionally replace its mappings and enrichments.
    Requires poweruser or admin role.
    """
    source = await repository.get_data_source_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # Update basic fields
    old_name = source.name
    if source_data.name is not None:
        # Check if new name conflicts with another source
        if await repository.data_source_name_exists(source_data.name, exclude_id=source_id):
            raise HTTPException(status_code=400, detail="Data source with this name already exists")
        await repository.update_service_alert_source_name(old_name, source_data.name)
    
    # Handle is_active changes
    if source_data.is_active is not None:
        old_status = source.is_active

        # If deactivating, delete all alerts from this source
        if old_status and not source_data.is_active:
            deleted_count = await repository.delete_alerts_for_data_source(source_id)

            logger.info(
                f"Deactivated data source {source_id} '{source.name}': "
                f"Deleted {deleted_count} associated alerts"
            )

    source = await repository.update_data_source(
        source_id,
        name=source_data.name,
        source_type=source_data.type,
        config=source_data.config,
        cron=source_data.cron,
        is_active=source_data.is_active,
        invalid_reference_policy=source_data.invalid_reference_policy,
        mappings=(
            [
                {
                    "entity_type": mapping_data.entity_type,
                    "key": mapping_data.key,
                    "value": mapping_data.value,
                }
                for mapping_data in source_data.mappings
            ]
            if source_data.mappings is not None
            else None
        ),
        enrichments=(
            [
                {
                    "enrichment_type": enrichment_data.enrichment_type,
                    "source_field": enrichment_data.source_field,
                    "key": enrichment_data.key,
                    "value": enrichment_data.value,
                    "sort_order": enrichment_data.sort_order,
                }
                for enrichment_data in source_data.enrichments
            ]
            if source_data.enrichments is not None
            else None
        ),
    )

    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # Update cron job: only schedule if active, otherwise remove
    if source.is_active and source.cron:
        await get_datasource_scheduler_service().schedule_data_source_import(source.id, source.name, source.cron)
    else:
        # Remove cron job if inactive or no cron expression
        await get_datasource_scheduler_service().schedule_data_source_import(source.id, source.name, None)

    return await _enrich_source_with_error_flag(source, repository)


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: int,
    _: CurrentPoweruser,
    repository: _Repo,
):
    """
    Delete a data source (cascades to mappings, alerts, and logs).
    Requires poweruser or admin role.
    """
    source = await repository.get_data_source_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # Delete log files before deleting the data source
    # (DB entries will be cascade-deleted automatically)
    await DatalogService(repository).delete_logs_for_data_source(source_id)
    
    # Remove cron job if exists
    await get_datasource_scheduler_service().schedule_data_source_import(source.id, source.name, None)
    
    await repository.delete_data_source(source_id)