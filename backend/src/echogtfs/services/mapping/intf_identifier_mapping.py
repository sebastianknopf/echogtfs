from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from echogtfs.services.database.intf_repository import RepositoryInterface


class IdentifierMappingInterface(ABC):
    """Interface for applying and loading identifier mappings."""

    @abstractmethod
    async def initialize(
        self,
        repository: RepositoryInterface,
        source_id: int,
    ) -> None:
        """Load mappings once for one pipeline run and store them internally."""
        raise NotImplementedError

    @abstractmethod
    def get_loaded_mapping_count(self) -> int:
        """Return the number of currently loaded mapping entries."""
        raise NotImplementedError

    @abstractmethod
    def apply_mapping(
        self,
        entity_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply loaded mappings to one informed-entity payload."""
        raise NotImplementedError