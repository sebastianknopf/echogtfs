from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface


class EntityEnrichmentInterface(ABC):
    """Interface for loading and applying entity enrichment rules."""

    @abstractmethod
    async def initialize(
        self,
        repository: SystemRepositoryInterface,
        source_id: int,
    ) -> None:
        """Load enrichments once for one pipeline run and store them internally."""
        raise NotImplementedError

    @abstractmethod
    def get_loaded_enrichment_count(self) -> int:
        """Return the number of currently loaded enrichment rules."""
        raise NotImplementedError

    @abstractmethod
    def apply_enrichment(
        self,
        alert_data: dict[str, Any],
        adapter_type: str,
    ) -> None:
        """Apply loaded enrichment rules in-place to one normalized alert payload."""
        raise NotImplementedError

    @abstractmethod
    async def apply_enrichment_async(
        self,
        alert_data: dict[str, Any],
        adapter_type: str,
    ) -> None:
        """Apply loaded enrichment rules in a worker thread."""
        raise NotImplementedError
