"""Shared contract for raw-data to trip-update transformers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TripUpdatesTransformerInterface(ABC):
    """Transforms raw datasource payloads into trip-update dictionaries."""

    @abstractmethod
    def transform(self, raw_data: Any) -> list[dict[str, Any]]:
        """Transform raw input payload into trip-update dictionaries."""

    @abstractmethod
    def get_runtime_duration_ms(self) -> float:
        """Return the duration of the last transform run in milliseconds."""
