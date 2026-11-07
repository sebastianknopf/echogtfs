"""Conflict filter options router."""

from typing import Annotated

from fastapi import APIRouter, Depends

from echogtfs.common.security import CurrentPoweruser
from echogtfs.enum.conflicts import ConflictType
from echogtfs.services.database import SystemRepositoryInterface, get_system_repository
from echogtfs.validation.schemas import (
    ConflictFilterOptionsResponse,
    ConflictTypeFilterObject,
    MonitoringDatasourceGroupObject,
)

router = APIRouter()

_Repo = Annotated[SystemRepositoryInterface, Depends(get_system_repository)]


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
