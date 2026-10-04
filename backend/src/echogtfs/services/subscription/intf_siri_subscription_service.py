from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SiriSubscriptionServiceInterface(ABC):
    """Manage SIRI subscriptions in the SIRI communication service."""

    @abstractmethod
    async def start_subscription(
        self,
        datasource_id: int,
        datasource_type: str,
        config: dict[str, Any],
    ) -> bool:
        """Create and activate a subscription for a SIRI datasource."""
        raise NotImplementedError

    @abstractmethod
    async def stop_subscription(self, datasource_id: int) -> bool:
        """Force-terminate and remove a SIRI subscription."""
        raise NotImplementedError

    @abstractmethod
    async def restart_subscription(
        self,
        datasource_id: int,
        datasource_type: str,
        config: dict[str, Any] | None,
    ) -> bool:
        """Restart or recreate a SIRI subscription."""
        raise NotImplementedError
