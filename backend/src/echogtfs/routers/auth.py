from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from echogtfs.common.config import settings
from echogtfs.common.extensions import limiter
from echogtfs.services.database import SystemRepositoryInterface, get_system_repository
from echogtfs.services.security import get_security_service
from echogtfs.validation.schemas import Token

router = APIRouter()

_ERR_INVALID_CREDENTIALS = "error.invalid_credentials"
_ERR_INACTIVE_USER = "error.inactive_user"

_Repo = Annotated[SystemRepositoryInterface, Depends(get_system_repository)]


@router.post(
        "/token", 
        responses={
            200: {
                "description": "Successful login",
                "model": Token,
            },
            400: {
                "description": "Inactive user",
                "content": {
                    "application/json": {
                        "example": {"detail": _ERR_INACTIVE_USER}
                    }
                },
            },
            401: {
                "description": "Invalid username or password",
                "content": {
                    "application/json": {
                        "example": {"detail": _ERR_INVALID_CREDENTIALS}
                    }
                },
            }
        }
    )
@limiter.limit(settings.login_rate_limit)
async def login(
    request: Request,  # required by slowapi
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    repository: _Repo,
) -> Token:
    """OAuth2 password-flow token endpoint. Authenticates an existing user in the system. Returns a Bearer JWT on success. This JWT must be used for all authenticated requests to the API."""
    user = await repository.get_user_by_username(form_data.username)

    if user is None or not get_security_service().verify_password(
        form_data.password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_ERR_INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_ERR_INACTIVE_USER,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Token(
        access_token=get_security_service().create_access_token(user.username),
        token_type="bearer",
    )
