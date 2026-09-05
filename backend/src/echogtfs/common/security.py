import logging
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from starlette.middleware.base import BaseHTTPMiddleware

from echogtfs.services.security import get_security_service
from echogtfs.services.database.models import User

logger = logging.getLogger("uvicorn.error")

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/token",
    auto_error=False
)


async def _get_current_active_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    return await get_security_service().get_current_active_user(request, token)


async def _get_current_superuser(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    return await get_security_service().get_current_superuser(request, token)


async def _get_current_poweruser_or_admin(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    return await get_security_service().get_current_poweruser_or_admin(request, token)


CurrentUser = Annotated[User, Depends(_get_current_active_user)]
CurrentSuperuser = Annotated[User, Depends(_get_current_superuser)]
CurrentPoweruser = Annotated[User, Depends(_get_current_poweruser_or_admin)]


class SlidingTokenMiddleware(BaseHTTPMiddleware):
    """Issue a renewed JWT token on successful authenticated requests."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if 200 <= response.status_code < 300:
            user = getattr(request.state, "user", None)
            if user is not None:
                response.headers["X-New-Token"] = get_security_service().create_access_token(user.username)
                logger.info("[SlidingToken] Issued new token for user: %s", user.username)
            else:
                logger.debug("[SlidingToken] No user in request.state for %s", request.url.path)

        return response
