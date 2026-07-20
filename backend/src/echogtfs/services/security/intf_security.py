from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta

from fastapi import Request

from echogtfs.services.database.models import User


class SecurityServiceInterface(ABC):
    """Interface for authentication and authorization operations."""

    @abstractmethod
    def hash_password(self, password: str) -> str:
        """Return a bcrypt hash for a plain password."""
        raise NotImplementedError

    @abstractmethod
    def verify_password(self, plain: str, hashed: str) -> bool:
        """Return True when plain password matches its bcrypt hash."""
        raise NotImplementedError

    @abstractmethod
    def create_access_token(self, subject: str, expires_delta: timedelta | None = None) -> str:
        """Create and sign a JWT access token for one subject."""
        raise NotImplementedError

    @abstractmethod
    async def get_current_user(self, request: Request, token: str) -> User:
        """Resolve and return authenticated user from bearer token."""
        raise NotImplementedError

    @abstractmethod
    async def get_current_active_user(self, request: Request, token: str) -> User:
        """Resolve user and require active account state."""
        raise NotImplementedError

    @abstractmethod
    async def get_current_superuser(self, request: Request, token: str) -> User:
        """Resolve user and require superuser permissions."""
        raise NotImplementedError

    @abstractmethod
    async def get_current_poweruser_or_admin(self, request: Request, token: str) -> User:
        """Resolve user and require technical-contact or superuser permissions."""
        raise NotImplementedError