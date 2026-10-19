"""Internal endpoint for synchronously executing any active data source."""

from fastapi import APIRouter, HTTPException, Request

from echogtfs.services.scheduler import get_datasource_scheduler_service
from echogtfs.services.scheduler.push_service_error import PushServiceError
from echogtfs.validation.schemas import PushResultResponse

router = APIRouter()


@router.post(
    "/datasource/{source_id}",
    response_model=PushResultResponse,
    include_in_schema=False,
)
async def execute_datasource(source_id: int, request: Request) -> PushResultResponse:
    """Execute a data source synchronously without authentication."""
    payload = await request.body()
    content_type = request.headers.get("content-type")

    try:
        stats = await get_datasource_scheduler_service().run_internal_push_task(
            source_id,
            payload,
            content_type,
        )
    except PushServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return PushResultResponse(**stats)
