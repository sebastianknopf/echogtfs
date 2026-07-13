from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.services.database.models import ServiceAlert, User


class RepositoryInterface(ABC):
    """Interface for database repositories."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize repository resources and validate connectivity."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close repository resources."""
        raise NotImplementedError

    @abstractmethod
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a managed database session owned by the repository."""
        raise NotImplementedError
    
    @abstractmethod
    async def get_app_setting(self, key: str) -> str | None:
        """Return app setting value for key or None when setting does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def set_app_setting(self, key: str, value: str) -> None:
        """Create or update one app setting value by key."""
        raise NotImplementedError

    @abstractmethod
    async def get_all_app_settings(self) -> dict[str, str]:
        """Return all app settings as key-value mapping."""
        raise NotImplementedError

    @abstractmethod
    async def get_user_by_id(self, user_id: int) -> User | None:
        """Return one user by id, or None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def get_user_by_username(self, username: str) -> User | None:
        """Return one user by username, or None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def user_exists_by_username_or_email(self, username: str, email: str) -> bool:
        """Return True when a user exists with the given username or email."""
        raise NotImplementedError

    @abstractmethod
    async def list_users(self) -> list[User]:
        """Return all users ordered by creation time."""
        raise NotImplementedError

    @abstractmethod
    async def create_user(
        self,
        username: str,
        email: str,
        hashed_password: str,
        *,
        is_active: bool = True,
        is_superuser: bool = False,
        is_technical_contact: bool = False,
    ) -> User:
        """Create and persist one user."""
        raise NotImplementedError

    @abstractmethod
    async def update_user(
        self,
        user_id: int,
        *,
        email: str | None = None,
        hashed_password: str | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
        is_technical_contact: bool | None = None,
    ) -> User | None:
        """Update mutable user fields and return updated user, or None when not found."""
        raise NotImplementedError

    @abstractmethod
    async def delete_user(self, user_id: int) -> bool:
        """Delete one user by id. Returns True when a row was deleted."""
        raise NotImplementedError

    @abstractmethod
    async def get_realtime_service_alerts(self) -> list[ServiceAlert]:
        """Return active realtime service alerts with all required relationships."""
        raise NotImplementedError
