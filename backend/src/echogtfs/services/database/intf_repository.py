from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.services.database.models import ServiceAlert


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
    async def get_realtime_service_alerts(self) -> list[ServiceAlert]:
        """Return active realtime service alerts with all required relationships."""
        raise NotImplementedError
