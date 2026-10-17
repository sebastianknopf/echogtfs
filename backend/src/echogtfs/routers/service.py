"""Status endpoints for the SIRI communication service."""

from fastapi import APIRouter
from echogtfs.common.security import CurrentUser
from echogtfs.services.subscription import get_siri_subscription_service

router = APIRouter()



@router.get("/health", include_in_schema=False)
async def siri_health(_: CurrentUser) -> bool:
    """Return whether the SIRI communication service is running."""
    return await get_siri_subscription_service().is_subscription_service_running()
