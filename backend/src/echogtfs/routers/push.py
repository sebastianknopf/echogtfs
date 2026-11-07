"""
Generic push API for event-based data sources.

Endpoint protected via JWT bearer token (API role and above) that lets
external systems synchronously feed a payload into one EVENT_BASED data source.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from echogtfs.common.security import CurrentApiUser
from echogtfs.services.database import get_system_repository
from echogtfs.services.database.models import AppSetting
from echogtfs.services.scheduler import get_datasource_scheduler_service
from echogtfs.services.scheduler.push_service_error import PushServiceError
from echogtfs.validation.schemas import PushResultResponse

router = APIRouter()
logger = logging.getLogger("uvicorn")

_ERR_PUSH_API_DISABLED = "error.push_api_disabled"


async def check_push_api_enabled() -> None:
    """Raise 403 if the push API feature switch is disabled."""
    rows = await get_system_repository().get_all_app_settings()

    if rows.get(AppSetting.KEY_PUSH_API_ENABLED, "false").lower() != "true":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ERR_PUSH_API_DISABLED)

@router.post(
    "/datasource/{source_id}",
    response_model=PushResultResponse,
    responses={
        401: {
            "description": "Unauthorized Access",
            "content": {
                "application/json": {
                    "example": {"detail": "error.401_unauthorized"}
                }
            }
        },
        403: {
            "description": "Push API disabled, or data source not active / not event-based",
            "content": {
                "application/json": {
                    "example": {"detail": "error.source_not_active"}
                }
            }
        },
        404: {
            "description": "Data source not found",
            "content": {
                "application/json": {
                    "example": {"detail": "error.source_not_found"}
                }
            }
        },
        409: {
            "description": "Data source is already running",
            "content": {
                "application/json": {
                    "example": {"detail": "error.source_already_running"}
                }
            }
        },
        422: {
            "description": "The pushed payload could not be processed",
            "content": {
                "application/json": {
                    "example": {"detail": "error.invalid_input"}
                }
            }
        }
    }
)
async def push_datasource(
    source_id: int,
    request: Request,
    _user: CurrentApiUser,
    _: Annotated[None, Depends(check_push_api_enabled)],
) -> PushResultResponse:
    """
    Push a payload into one event-based data source and synchronize it synchronously.

    The request body and its Content-Type header are handed over to the data
    source's adapter as-it-is. Only data sources that are active and configured
    for event-based execution can be triggered this way. Requires a bearer token
    of an account with the API role or above.
    """
    payload = await request.body()
    content_type = request.headers.get("content-type")

    try:
        stats = await get_datasource_scheduler_service().run_push_task(source_id, payload, content_type)
    except PushServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return PushResultResponse(**stats)
