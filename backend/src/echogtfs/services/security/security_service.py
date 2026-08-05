from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Request, status

from echogtfs.common.config import settings
from echogtfs.services.database import SystemRepositoryInterface
from echogtfs.services.database.models import User
from echogtfs.services.security.intf_security import SecurityServiceInterface


class SecurityService(SecurityServiceInterface):
    """Repository-backed security service."""

    _instance: SecurityService | None = None

    def __new__(cls, repository: SystemRepositoryInterface) -> SecurityService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(self, repository: SystemRepositoryInterface):
        self._repository = repository

    @staticmethod
    def _credentials_exception() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify_password(self, plain: str, hashed: str) -> bool:
        return bcrypt.checkpw(plain.encode(), hashed.encode())

    def create_access_token(self, subject: str, expires_delta: timedelta | None = None) -> str:
        expire = datetime.now(UTC) + (
            expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
        )

        return jwt.encode(
            {"sub": subject, "exp": expire},
            settings.secret_key,
            algorithm=settings.algorithm,
        )

    async def get_current_user(self, request: Request, token: str) -> User:
        credentials_exception = self._credentials_exception()

        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            username: str | None = payload.get("sub")
            
            if username is None:
                raise credentials_exception
        except jwt.InvalidTokenError:
            raise credentials_exception

        user = await self._repository.get_user_by_username(username)
        if user is None:
            raise credentials_exception

        request.state.user = user

        return user

    async def get_current_active_user(self, request: Request, token: str) -> User:
        current_user = await self.get_current_user(request, token)
        
        if not current_user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

        return current_user

    async def get_current_superuser(self, request: Request, token: str) -> User:
        current_user = await self.get_current_active_user(request, token)
        
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        return current_user

    async def get_current_poweruser_or_admin(self, request: Request, token: str) -> User:
        current_user = await self.get_current_active_user(request, token)
        if not (current_user.is_technical_contact or current_user.is_superuser):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        return current_user