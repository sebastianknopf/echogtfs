"""Capabilities endpoint listing the optional components available in this installation."""

from fastapi import APIRouter

from echogtfs.common.security import CurrentUser
from echogtfs.services.subscription import get_siri_subscription_service

router = APIRouter()


@router.get("", include_in_schema=False)
async def get_capabilities(_: CurrentUser) -> list[str]:
    """Return the capabilities of the running system."""
    capabilities = ["echobase"]

    if await get_siri_subscription_service().is_subscription_service_available():
        capabilities.append("siricomservice")

    return capabilities
