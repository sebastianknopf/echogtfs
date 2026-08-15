from __future__ import annotations

import re
from typing import Any

from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.mapping.intf_identifier_mapping import IdentifierMappingInterface


class IdentifierMappingService(IdentifierMappingInterface):
    """Service for loading and applying identifier mappings."""

    def __init__(self) -> None:
        self._mappings: dict[str, dict[str, str]] = {}

    async def initialize(
        self,
        repository: SystemRepositoryInterface,
        source_id: int,
    ) -> None:
        """Load mappings grouped by entity type for one data source."""
        self._mappings = await repository.list_data_source_mappings_grouped(source_id)

    def get_loaded_mapping_count(self) -> int:
        """Return the number of loaded mappings across all entity types."""
        return sum(len(group) for group in self._mappings.values())

    def apply_mapping(
        self,
        entity_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply configured mappings to one informed entity."""
        mapped_entity: dict[str, Any] = entity_data.copy()

        if "agency_id" in mapped_entity and mapped_entity["agency_id"]:
            mapped_entity["agency_id"] = self._apply_mapping_with_wildcard(
                str(mapped_entity["agency_id"]),
                self._mappings.get("agency", {}),
            )

        if "route_id" in mapped_entity and mapped_entity["route_id"]:
            mapped_entity["route_id"] = self._apply_mapping_with_wildcard(
                str(mapped_entity["route_id"]),
                self._mappings.get("route", {}),
            )

        if "stop_id" in mapped_entity and mapped_entity["stop_id"]:
            mapped_entity["stop_id"] = self._apply_mapping_with_wildcard(
                str(mapped_entity["stop_id"]),
                self._mappings.get("stop", {}),
            )

        return mapped_entity

    def _apply_mapping_with_wildcard(
        self,
        original_value: str,
        mappings: dict[str, str],
    ) -> str:
        """Resolve one identifier against exact and wildcard mapping rules."""
        if original_value in mappings:
            return mappings[original_value]

        for mapping_key, mapping_value in mappings.items():
            if "*" not in mapping_key:
                continue

            if mapping_key.endswith("*"):
                prefix = mapping_key[:-1]
                if original_value.startswith(prefix):
                    return mapping_value
                continue

            pattern = re.escape(mapping_key).replace(r"\*", ".*")
            if re.fullmatch(pattern, original_value):
                return mapping_value

        return original_value