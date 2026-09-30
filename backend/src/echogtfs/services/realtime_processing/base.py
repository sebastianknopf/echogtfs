from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
import logging
import uuid
from typing import Any

from echogtfs.common.global_id import GlobalId
from echogtfs.enum.gtfsrt import AssignmentType
from echogtfs.enum.system import IncorrectStopIdHandling, InvalidReferencePolicy
from echogtfs.services.caching.intf_caching_service import CachingServiceInterface
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.enrichment.intf_entity_enrichment import EntityEnrichmentInterface
from echogtfs.services.mapping.intf_identifier_mapping import IdentifierMappingInterface
from echogtfs.services.matching.intf_matching_service import MatchingServiceInterface
from echogtfs.services.matching.matching_service import MatchingService

logger = logging.getLogger("uvicorn")


class RealtimeProcessingServiceBase:
    """Shared infrastructure for realtime entity processing services."""

    def __init__(self, config: dict[str, Any], entity_enrichment_service: EntityEnrichmentInterface, identifier_mapping_service: IdentifierMappingInterface, caching_service: CachingServiceInterface, matching_service: MatchingServiceInterface | None = None):
        self.config = config
        self._entity_enrichment_service = entity_enrichment_service
        self._identifier_mapping_service = identifier_mapping_service
        self._caching_service = caching_service
        self._matching_service = matching_service

    def get_adapter_type(self) -> str:
        return str(self.config.get("_adapter_type", "datasource"))

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError):
            return False

    def _make_unique_id(self, original_id: str, source_name: str) -> uuid.UUID:
        if self._is_uuid(original_id):
            return uuid.UUID(original_id)
        
        namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
        
        return uuid.uuid5(namespace, f"{source_name}-{original_id}")

    async def _load_gtfs_entities(
        self,
        repository: GtfsRepositoryInterface,
    ) -> dict[str, set[str]]:
        """Load all GTFS entity IDs into memory for fast validation.
        
        Returns a dictionary with sets of valid IDs:
        {
            "agency": {"agency_1", "agency_2", ...},
            "route": {"route_1", "route_2", ...},
            "stop": {"stop_1", "stop_2", ...}
        }
        
        Args:
            db: Database session
        """
        logger.info("[Datasource] Loading GTFS entities into memory for validation")
        gtfs_entities = await repository.list_gtfs_entity_ids()
        
        logger.info(
            f"[Datasource] Loaded {len(gtfs_entities['agency'])} agencies, "
            f"{len(gtfs_entities['route'])} routes, {len(gtfs_entities['stop'])} stops"
        )
        
        return gtfs_entities

    def _validate_entity(
        self, 
        entity_data: dict[str, Any], 
        gtfs_entities: dict[str, set[str]]
    ) -> bool:
        """Validate if an informed entity references valid GTFS entities.
        
        Args:
            entity_data: Dictionary with entity fields (agency_id, route_id, stop_id)
            gtfs_entities: Dictionary of valid GTFS IDs from _load_gtfs_entities()
        
        Returns:
            True if all referenced entities are valid, False otherwise
        """
        return self._is_entity_valid_flags(self._entity_validation_flags(entity_data, gtfs_entities))

    @staticmethod
    def _is_entity_valid_flags(validation_flags: dict[str, bool]) -> bool:
        """Return aggregate validity from per-reference validation flags."""
        return bool(
            validation_flags["is_agency_valid"]
            and validation_flags["is_route_valid"]
            and validation_flags["is_stop_valid"]
            and validation_flags["is_trip_valid"]
        )

    @staticmethod
    def _merge_provided_entity_validation_flags(
        entity_data: dict[str, Any],
        computed_flags: dict[str, bool],
    ) -> dict[str, bool]:
        """Combine provided per-reference validity with computed validation using logical AND."""
        merged_flags = dict(computed_flags)
        for key in ("is_agency_valid", "is_route_valid", "is_stop_valid", "is_trip_valid"):
            provided_value = entity_data.get(key)
            if provided_value is not None:
                merged_flags[key] = bool(provided_value) and bool(merged_flags[key])

        return merged_flags

    def _entity_validation_flags(
        self,
        entity_data: dict[str, Any],
        gtfs_entities: dict[str, set[str]],
    ) -> dict[str, bool]:
        """Validate per informed-entity reference type and provide aggregate validity."""
        has_agency_id = bool(entity_data.get("agency_id"))
        has_route_id = bool(entity_data.get("route_id"))
        has_stop_id = bool(entity_data.get("stop_id"))
        has_trip_id = bool(entity_data.get("trip_id"))
        has_primary_reference = has_agency_id or has_route_id or has_stop_id

        is_agency_valid = (not has_agency_id) or (entity_data["agency_id"] in gtfs_entities["agency"])
        is_route_valid = (not has_route_id) or (entity_data["route_id"] in gtfs_entities["route"])
        is_stop_valid = (not has_stop_id) or (entity_data["stop_id"] in gtfs_entities["stop"])

        # Trip references are currently not validated against GTFS and therefore
        # are treated as invalid when they are the only reference.
        is_trip_valid = (not has_trip_id) or has_primary_reference

        if has_trip_id and not has_primary_reference:
            logger.debug(
                f"[{self.get_adapter_type()}] Entity has only trip_id without other references - "
                f"marking as invalid (trip references not managed): trip_id={entity_data.get('trip_id')}"
            )

        return {
            "is_agency_valid": is_agency_valid,
            "is_route_valid": is_route_valid,
            "is_stop_valid": is_stop_valid,
            "is_trip_valid": is_trip_valid,
        }

    def _validate_and_clean_entity_elements(
        self, 
        entity_data: dict[str, Any], 
        gtfs_entities: dict[str, set[str]]
    ) -> tuple[dict[str, Any], bool]:
        """Validate and clean individual fields within an informed entity.
        
        Removes invalid entity references (agency_id, route_id, stop_id) from the entity
        while keeping valid ones. This is used by DISCARD_INVALID_ELEMENTS policy.
        
        Args:
            entity_data: Dictionary with entity fields (agency_id, route_id, stop_id, etc.)
            gtfs_entities: Dictionary of valid GTFS IDs from _load_gtfs_entities()
        
        Returns:
            Tuple of (cleaned_entity_data, has_any_valid_reference)
            - cleaned_entity_data: Entity with invalid fields removed
            - has_any_valid_reference: True if at least one valid reference remains
        """
        # Create a copy to avoid modifying the original
        cleaned_entity = entity_data.copy()
        has_any_valid_reference = False
        removed_fields = []
        
        validation_flags = self._merge_provided_entity_validation_flags(
            cleaned_entity,
            self._entity_validation_flags(cleaned_entity, gtfs_entities),
        )

        # Check and clean agency_id
        if cleaned_entity.get("agency_id"):
            if not validation_flags["is_agency_valid"]:
                removed_fields.append(f"agency_id={cleaned_entity['agency_id']}")
                cleaned_entity["agency_id"] = None
            else:
                has_any_valid_reference = True
        
        # Check and clean route_id
        if cleaned_entity.get("route_id"):
            if not validation_flags["is_route_valid"]:
                removed_fields.append(f"route_id={cleaned_entity['route_id']}")
                cleaned_entity["route_id"] = None
            else:
                has_any_valid_reference = True
        
        # Check and clean stop_id
        if cleaned_entity.get("stop_id"):
            if not validation_flags["is_stop_valid"]:
                removed_fields.append(f"stop_id={cleaned_entity['stop_id']}")
                cleaned_entity["stop_id"] = None
            else:
                has_any_valid_reference = True
        
        # Trip references are not managed - if only trip_id remains after cleaning,
        # this entity has no valid references (trip_id alone is not sufficient)
        if cleaned_entity.get("trip_id") and not has_any_valid_reference:
            removed_fields.append(f"trip_id={cleaned_entity['trip_id']} (not managed)")
            cleaned_entity["trip_id"] = None
        
        # Log removed fields
        if removed_fields:
            logger.debug(
                f"[{self.get_adapter_type()}] Removed invalid fields from entity: "
                f"{', '.join(removed_fields)}"
            )
        
        return cleaned_entity, has_any_valid_reference

    def _deduplicate_entities(self, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Remove duplicate informed entities from a list.
        
        Two entities are considered duplicates if they have the same values for:
        agency_id, route_id, route_type, stop_id, trip_id, and direction_id.
        
        Args:
            entities: List of entity dictionaries
            
        Returns:
            List with duplicates removed (preserving order, keeping first occurrence)
        """
        seen = set()
        deduplicated = []
        
        for entity in entities:
            # Create a tuple of relevant fields for comparison.
            entity_key = (
                entity.get("agency_id"),
                entity.get("route_id"),
                entity.get("route_type"),
                entity.get("stop_id"),
                entity.get("trip_id"),
                entity.get("direction_id"),
            )
            
            if entity_key not in seen:
                seen.add(entity_key)
                deduplicated.append(entity)
        
        return deduplicated

    def _normalize_fetched_payload(
        self,
        fetched_payload: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Normalize fetched datasource payload into (record_type, records)."""
        if isinstance(fetched_payload, dict):
            record_type = fetched_payload.get("record_type")
            records = fetched_payload.get("records")

            if not isinstance(record_type, str):
                raise ValueError("Fetched payload is missing string field 'record_type'")

            if not isinstance(records, list):
                raise ValueError("Fetched payload is missing list field 'records'")

            return record_type, records

        raise ValueError(
            "Fetched payload must be a dict with 'record_type' and 'records'"
        )

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        """Accept datetime input and return None for unsupported types."""
        if isinstance(value, datetime):
            return value

        return None

    @staticmethod
    def _parse_operation_day(start_date: Any) -> date | None:
        """Parse a GTFS-RT start_date (YYYYMMDD) into a date, or None if invalid."""
        if not isinstance(start_date, str) or not start_date:
            return None

        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(start_date, fmt).date()
            except ValueError:
                continue

        return None

    def _record_uuid(self, record: dict[str, Any], source_name: str, *, fallback_key: str, kind: str) -> uuid.UUID:
        """Build deterministic UUID for one record using id or fallback key."""
        record_key = str(record.get("id") or record.get(fallback_key) or "")
        if not record_key:
            raise ValueError(f"{kind} record is missing 'id' or '{fallback_key}'")

        return self._make_unique_id(record_key, source_name)

    async def _run_cpu_bound(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run CPU-bound synchronous work in a worker thread.

        This helper remains available for datasource fetch/parse stages that still
        execute on the async caller, while the bulk sync pipeline itself runs in a
        dedicated process and uses direct synchronous calls.
        """
        return await asyncio.to_thread(func, *args, **kwargs)
