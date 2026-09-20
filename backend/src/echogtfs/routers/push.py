"""
Generic push API for event-based data sources.

Public endpoint (optionally protected via Basic Auth) that lets external
systems synchronously feed a payload into one EVENT_BASED data source.
"""

import base64
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from echogtfs.services.database import get_system_repository
from echogtfs.services.database.models import AppSetting
from echogtfs.services.scheduler import get_datasource_scheduler_service
from echogtfs.services.scheduler.push_service_error import PushServiceError
from echogtfs.services.security import get_security_service
from echogtfs.validation.schemas import PushResultResponse

router = APIRouter()
logger = logging.getLogger("uvicorn")

_ERR_PUSH_API_DISABLED = "error.push_api_disabled"
_ERR_INVALID_CREDENTIALS = "error.invalid_credentials"


async def _get_push_api_settings() -> tuple[bool, str, str]:
    """Load the push API enabled flag and optional basic-auth credentials from settings."""
    repository = get_system_repository()
    rows = await repository.get_all_app_settings()

    return (
        rows.get(AppSetting.KEY_PUSH_API_ENABLED, "false").lower() == "true",
        rows.get(AppSetting.KEY_PUSH_API_USERNAME, ""),
        rows.get(AppSetting.KEY_PUSH_API_PASSWORD, ""),
    )


async def check_push_api_auth(request: Request) -> None:
    """
    Basic Auth for the push API, gated by a dedicated enabled flag.

    Raises 403 if the push API is disabled. If Basic Auth credentials are
    configured, raises 401/422 for missing/invalid credentials.
    """
    enabled, configured_username, hashed_password = await _get_push_api_settings()

    if not enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ERR_PUSH_API_DISABLED)

    # If no credentials configured, allow access
    if not configured_username or not hashed_password:
        return

    # Credentials are configured, require Basic Auth
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Decode and verify credentials
    try:
        encoded = auth_header[6:]  # Remove "Basic " prefix
        decoded = base64.b64decode(encoded).decode("utf-8")
        provided_username, _, password = decoded.partition(":")

        if provided_username != configured_username:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_ERR_INVALID_CREDENTIALS,
                headers={"WWW-Authenticate": "Basic"},
            )

        if not get_security_service().verify_password(password, hashed_password):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_ERR_INVALID_CREDENTIALS,
                headers={"WWW-Authenticate": "Basic"},
            )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_ERR_INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Basic"},
        )


@router.post(
    "/datasource/{source_id}",
    response_model=PushResultResponse,
    responses={
        401: {
            "description": "Unauthorized Access",
            "content": {
                "application/json": {
                    "example": {"detail": "Authentication required"}
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
            "description": "Invalid credentials, or the pushed payload could not be processed",
            "content": {
                "application/json": {
                    "example": {"detail": "error.invalid_credentials"}
                }
            }
        }
    }
)
async def push_datasource(
    source_id: int,
    request: Request,
    _: Annotated[None, Depends(check_push_api_auth)],
) -> PushResultResponse:
    """
    Push a payload into one event-based data source and synchronize it synchronously.

    The request body and its Content-Type header are handed over to the data
    source's adapter as-is. Only data sources that are active and configured
    for event-based execution can be triggered this way.
    """
    payload = await request.body()
    content_type = request.headers.get("content-type")

    try:
        stats = await get_datasource_scheduler_service().run_push_task(source_id, payload, content_type)
    except PushServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return PushResultResponse(**stats)
