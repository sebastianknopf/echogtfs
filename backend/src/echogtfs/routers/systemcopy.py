from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from echogtfs.common.security import CurrentSuperuser
from echogtfs.services.database import get_system_repository
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.systemcopy import SystemCopyInterface, SystemCopyService
from echogtfs.validation.schemas import SystemCopyExportSelection, SystemCopyImportSummary

router = APIRouter()

_ERR_INVALID_INPUT = "error.invalid_input"

_Repo = Annotated[SystemRepositoryInterface, Depends(get_system_repository)]


def create_systemcopy_service(repository: _Repo) -> SystemCopyInterface:
    """Create one System Copy service instance for the current dependency scope."""
    return SystemCopyService(repository)


_SystemCopy = Annotated[SystemCopyInterface, Depends(create_systemcopy_service)]


@router.post("/export")
async def export_system_copy(
    payload: SystemCopyExportSelection,
    _: CurrentSuperuser,
    service: _SystemCopy,
) -> StreamingResponse:
    """Export selected system table domains as a ZIP archive."""
    try:
        archive_bytes = await service.export_zip(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"system-copy-{timestamp}.zip"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}

    return StreamingResponse(
        iter([archive_bytes]),
        media_type="application/zip",
        headers=headers,
        status_code=status.HTTP_200_OK,
    )


@router.post("/import", response_model=SystemCopyImportSummary)
async def import_system_copy(
    _: CurrentSuperuser,
    service: _SystemCopy,
    file: UploadFile = File(...),
) -> SystemCopyImportSummary:
    """Import a previously exported system copy ZIP archive."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_ERR_INVALID_INPUT,
        )

    archive_bytes = await file.read()
    if not archive_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_ERR_INVALID_INPUT,
        )

    try:
        summary = await service.import_zip(archive_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return SystemCopyImportSummary.model_validate(summary)
