"""Base contract for datasources that require subscription management."""

from abc import abstractmethod
from typing import Any

from echogtfs.datasources.base import DatasourceBase


class SubscriptionDatasourceBase(DatasourceBase):
    """Abstract datasource base for subscription-managed data sources."""

    @abstractmethod
    def is_subscription_required(self) -> bool:
        """Return whether this datasource requires an active subscription."""

    @abstractmethod
    def get_subscription_params(self) -> dict[str, Any]:
        """Return the parameters required to configure the subscription."""
