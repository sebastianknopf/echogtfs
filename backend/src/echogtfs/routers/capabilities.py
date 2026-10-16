"""Capabilities endpoint listing the optional components available in this installation."""

import httpx
from fastapi import APIRouter

from echogtfs.common.security import CurrentUser

router = APIRouter()

_SIRI_SERVICE_READY_URL = "http://siricomservice:8080/health/ready"


async def _is_siricomservice_ready() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            response = await client.get(_SIRI_SERVICE_READY_URL)
    except httpx.HTTPError:
        return False

    return response.status_code == 200


@router.get("", include_in_schema=False)
async def get_capabilities(_: CurrentUser) -> list[str]:
    """Return the capabilities of the running system."""
    capabilities = ["echobase"]

    if await _is_siricomservice_ready():
        capabilities.append("siricomservice")

    return capabilities
