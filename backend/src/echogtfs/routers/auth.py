from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.config import settings
from echogtfs.database import get_db
from echogtfs.extensions import limiter
from echogtfs.models import User
from echogtfs.schemas import Token
from echogtfs.security import create_access_token, verify_password

router = APIRouter()

_DB = Annotated[AsyncSession, Depends(get_db)]


@router.post("/token", response_model=Token)
@limiter.limit(settings.login_rate_limit)
async def login(
    request: Request,  # required by slowapi
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: _DB,
) -> Token:
    """OAuth2 password-flow token endpoint. Returns a Bearer JWT on success."""
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )

    return Token(access_token=create_access_token(user.username), token_type="bearer")
