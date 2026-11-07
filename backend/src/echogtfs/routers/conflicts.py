"""Conflict filter options router."""

from typing import Annotated

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response

from echogtfs.common.security import CurrentPoweruser
from echogtfs.enum.conflicts import ConflictType
from echogtfs.services.conflict.conflict_csv_export_service import ConflictCsvExportService
from echogtfs.services.database import (
    RealtimeRepositoryInterface,
    SystemRepositoryInterface,
    get_realtime_repository,
    get_system_repository,
)
from echogtfs.validation.schemas import (
    ConflictFilterOptionsResponse,
    ConflictTypeFilterObject,
    MonitoringDatasourceGroupObject,
)

router = APIRouter()

_Repo = Annotated[SystemRepositoryInterface, Depends(get_system_repository)]
_RealtimeRepo = Annotated[RealtimeRepositoryInterface, Depends(get_realtime_repository)]


@router.get("/export", response_class=Response)
async def export_conflicts_csv(
    _: CurrentPoweruser,
    repository: _Repo,
    realtime_repository: _RealtimeRepo,
    data_source_id: Annotated[int | None, Query(alias="datasourceId")] = None,
) -> Response:
    """Export the current conflicts as CSV file."""
    service = ConflictCsvExportService(
        system_repository=repository,
        realtime_repository=realtime_repository,
    )
    
    content = await service.export_csv(filter_datasource_id=data_source_id)
    filename = f"conflicts-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/filters", response_model=ConflictFilterOptionsResponse)
async def get_conflict_filter_options(
    _: CurrentPoweruser,
    repository: _Repo,
) -> ConflictFilterOptionsResponse:
    """Return available data sources and conflict types for the conflicts view."""
    data_sources = [
        MonitoringDatasourceGroupObject(id=source.id, name=source.name)
        for source in await repository.list_data_sources()
        if source.is_active
    ]
    conflict_types = [
        ConflictTypeFilterObject(code=conflict_type, name=conflict_type.name)
        for conflict_type in ConflictType
    ]
    return ConflictFilterOptionsResponse(
        data_sources=data_sources,
        conflict_types=conflict_types,
    )
