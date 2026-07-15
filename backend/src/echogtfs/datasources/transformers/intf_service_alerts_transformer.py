"""Shared contract for raw-data to service-alert transformers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ServiceAlertsTransformerInterface(ABC):
    """Transforms raw datasource payloads into service alert dictionaries."""

    @abstractmethod
    def transform(self, raw_data: Any) -> list[dict[str, Any]]:
        """Transform raw input payload into service alert dictionaries."""
