from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SiriSubscriptionServiceInterface(ABC):
    """Manage SIRI subscriptions in the SIRI communication service."""

    @abstractmethod
    async def is_subscription_service_running(self) -> bool:
        """Return whether the SIRI communication service is running."""
        raise NotImplementedError

    @abstractmethod
    async def is_subscription_service_available(self) -> bool:
        """Return whether the SIRI communication service is ready to accept work."""
        raise NotImplementedError

    @abstractmethod
    async def start_subscription(
        self,
        datasource_id: int,
        config: dict[str, Any],
    ) -> bool:
        """Create and activate a subscription for a SIRI datasource."""
        raise NotImplementedError

    @abstractmethod
    async def stop_subscription(self, datasource_id: int) -> bool:
        """Force-terminate and remove a SIRI subscription."""
        raise NotImplementedError

    @abstractmethod
    async def get_subscription_status(self, datasource_id: int) -> bool:
        """Return whether a datasource subscription is currently active."""
        raise NotImplementedError

    @abstractmethod
    async def restart_subscription(
        self,
        datasource_id: int,
        config: dict[str, Any] | None,
    ) -> bool:
        """Restart or recreate a SIRI subscription."""
        raise NotImplementedError
