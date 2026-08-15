"""Base datasource implementation for external data feeds."""

import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import date, datetime
import logging
import uuid
from time import perf_counter
from typing import Any

from echogtfs.common.global_id import GlobalId
from echogtfs.datasources.intf_datasource import DatasourceInterface
from echogtfs.enum.gtfsrt import AssignmentType
from echogtfs.enum.system import InvalidReferencePolicy
from echogtfs.services.matching.intf_matching_service import MatchingServiceInterface
from echogtfs.services.matching.matching_service import MatchingService
from echogtfs.services.caching import get_caching_service
from echogtfs.services.database import get_system_repository
from echogtfs.services.datalog import DatalogService
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.enrichment.entity_enrichtment_service import EntityEnrichmentService
from echogtfs.services.enrichment.intf_entity_enrichment import EntityEnrichmentInterface
from echogtfs.services.mapping.identifier_mapping_service import IdentifierMappingService
from echogtfs.services.mapping.intf_identifier_mapping import IdentifierMappingInterface

logger = logging.getLogger("uvicorn")


class DatasourceBase(DatasourceInterface):
    """
    Abstract base class for data sources.
    
    Each datasource handles fetching data from a specific external format
    and transforming it into internal persistence records.
    """
    
    # Each datasource must define its configuration schema
    # List of dicts with keys: name, type, label, required, placeholder, help_text
    CONFIG_SCHEMA: list[dict[str, Any]] = []
    
    def __init__(self, config: dict[str, Any]):
        """
        Initialize the datasource with configuration.
        
        Args:
            config: Configuration dictionary containing at minimum:
                    - endpoint: URL endpoint for the data source
                    Additional fields depend on the specific adapter.
        """
        self.config = config
        self._entity_enrichment_service: EntityEnrichmentInterface = EntityEnrichmentService()
        self._identifier_mapping_service: IdentifierMappingInterface = IdentifierMappingService()
        self._matching_service: MatchingServiceInterface | None = None
        self._validate_config()
    
    @abstractmethod
    def _validate_config(self) -> None:
        """
        Validate the datasource configuration.
        
        Raises:
            ValueError: If required configuration fields are missing or invalid
        """
        pass
    
    @abstractmethod
    async def _fetch_records(self) -> dict[str, Any]:
        """
        Fetch realtime records from the external data source.
        
        Returns:
            Dialect-defined payload ready for sync_records().
            Supported return shapes and per-record model contracts are documented in
            docs/dev/transformation.md.
        """
        pass
    
    def _is_uuid(self, value: str) -> bool:
        """
        Check if a string is a valid UUID.
        
        Args:
            value: String to check
            
        Returns:
            True if value is a valid UUID, False otherwise
        """
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError):
            return False
    
    def _make_unique_id(self, original_id: str, source_name: str) -> uuid.UUID:
        """
        Create a unique UUID for a datasource record based on its original ID and source.
        
        If the original ID is already a UUID, return it as-is.
        Otherwise, create a deterministic UUID using namespace UUID5.
        
        Args:
            original_id: Original record ID from external feed
            source_name: Name of the data source
            
        Returns:
            UUID object
        """
        if self._is_uuid(original_id):
            return uuid.UUID(original_id)
        
        # Create a deterministic UUID using namespace and source+ID combination
        # This ensures the same alert from the same source always gets the same UUID
        namespace = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')  # DNS namespace
        unique_name = f"{source_name}-{original_id}"

        return uuid.uuid5(namespace, unique_name)
    
    def get_datasource_type(self) -> str:
        """
        Get the type identifier of this datasource.
        
        Returns:
            Datasource type string (e.g., "sirilite", "gtfsrt")
        """
        return self.__class__.__name__.replace("Datasource", "").lower()

    # Backward-compatible alias used by existing log messages.
    def get_adapter_type(self) -> str:
        return self.get_datasource_type()
    
    @classmethod
    def get_config_schema(cls) -> list[dict[str, Any]]:
        """
        Get the configuration schema for this datasource.
        
        Returns:
            List of configuration field definitions
        """
        return [dict(field) for field in cls.CONFIG_SCHEMA]
    
    async def _log_request(
        self,
        source_id: int | None,
        request_url: str,
        request_headers: dict[str, str] | None,
        response_headers: dict[str, str] | None,
        response_status_code: int | None,
        response_content: str | None,
        response_content_type: str | None
    ) -> None:
        if not source_id:
            return

        try:
            save_dump = bool(self.config.get("_log_dumps", False))
            repository = get_system_repository()

            await DatalogService(repository).create_log_entry(
                data_source_id=source_id,
                request_url=request_url,
                response_content=response_content,
                request_headers=dict(request_headers) if request_headers else None,
                response_headers=dict(response_headers) if response_headers else None,
                response_mimetype=response_content_type,
                status_code=response_status_code,
                save_dump=save_dump,
            )
        except Exception as exc:
            logger.error(
                f"[{self.get_adapter_type()}] Failed to log request: {exc}",
                exc_info=True,
            )

    
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
        # Trip references are not managed/validated - if only trip_id is set,
        # mark the entity as invalid (trip_id without other references)
        has_trip_id = bool(entity_data.get("trip_id"))
        has_agency_id = bool(entity_data.get("agency_id"))
        has_route_id = bool(entity_data.get("route_id"))
        has_stop_id = bool(entity_data.get("stop_id"))
        
        # If only trip_id is set (without agency, route, or stop), mark as invalid
        # direction_id and route_type are just qualifiers, not primary references
        if has_trip_id and not has_agency_id and not has_route_id and not has_stop_id:
            logger.debug(
                f"[{self.get_adapter_type()}] Entity has only trip_id without other references - "
                f"marking as invalid (trip references not managed): trip_id={entity_data.get('trip_id')}"
            )
            return False
        
        # Check each entity type that is specified
        if entity_data.get("agency_id"):
            if entity_data["agency_id"] not in gtfs_entities["agency"]:
                return False
        
        if entity_data.get("route_id"):
            if entity_data["route_id"] not in gtfs_entities["route"]:
                return False
        
        if entity_data.get("stop_id"):
            if entity_data["stop_id"] not in gtfs_entities["stop"]:
                return False
        
        # If no entities are specified or all specified entities are valid
        return True
    
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
        
        # If entity is already marked as invalid (e.g., trip references),
        # don't clean it further - just return it as-is
        if entity_data.get("is_valid") is False:
            return cleaned_entity, False
        
        # Check and clean agency_id
        if cleaned_entity.get("agency_id"):
            if cleaned_entity["agency_id"] not in gtfs_entities["agency"]:
                removed_fields.append(f"agency_id={cleaned_entity['agency_id']}")
                cleaned_entity["agency_id"] = None
            else:
                has_any_valid_reference = True
        
        # Check and clean route_id
        if cleaned_entity.get("route_id"):
            if cleaned_entity["route_id"] not in gtfs_entities["route"]:
                removed_fields.append(f"route_id={cleaned_entity['route_id']}")
                cleaned_entity["route_id"] = None
            else:
                has_any_valid_reference = True
        
        # Check and clean stop_id
        if cleaned_entity.get("stop_id"):
            if cleaned_entity["stop_id"] not in gtfs_entities["stop"]:
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
            # Create a tuple of relevant fields for comparison (excluding is_valid)
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
    def _parse_service_datetime(start_date: str | None, time_value: str | None) -> datetime | None:
        """Parse GTFS service date/time pair to datetime, or None if incomplete/invalid."""
        if not start_date or not time_value:
            return None

        try:
            return datetime.strptime(f"{start_date} {time_value}", "%Y%m%d %H:%M:%S")
        except ValueError:
            return None

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

        try:
            return datetime.strptime(start_date, "%Y%m%d").date()
        except ValueError:
            return None

    def _record_uuid(self, record: dict[str, Any], source_name: str, *, fallback_key: str, kind: str) -> uuid.UUID:
        """Build deterministic UUID for one record using id or fallback key."""
        record_key = str(record.get("id") or record.get(fallback_key) or "")
        if not record_key:
            raise ValueError(f"{kind} record is missing 'id' or '{fallback_key}'")

        return self._make_unique_id(record_key, source_name)

    @staticmethod
    def _coerce_stop_time_for_sort(value: Any) -> datetime:
        """Best-effort datetime conversion used only for stop-event merge ordering."""
        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return datetime.max

        return datetime.max

    @staticmethod
    def _normalize_stop_id_for_matching(value: Any) -> str:
        """Normalize a stop ID to its level-3 global-ID form for matching purposes."""
        if value is None:
            return ""

        stop_id = str(value)
        if not stop_id:
            return ""

        if GlobalId.is_global_id(stop_id):
            return GlobalId.level(stop_id, 3)

        return stop_id

    async def _run_cpu_bound(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run CPU-bound synchronous work in a worker thread."""
        return await asyncio.to_thread(func, *args, **kwargs)

    def _propagate_trip_update_stop_events(
        self,
        stop_events: list[dict[str, Any]],
        nominal_stop_times: list[Any],
        *,
        treat_unexpected_stop_as_added_stop: bool,
        treat_missing_stop_as_canceled_stop: bool,
        is_complete_stop_sequence: bool,
    ) -> list[dict[str, Any]]:
        """Apply nominal-stop propagation and merge rules for one trip-update stop-event list."""
        if not nominal_stop_times:
            return [dict(event) for event in stop_events]

        propagated_events = [dict(event) for event in stop_events]

        nominal_by_stop_id: dict[str, Any] = {}
        nominal_order: list[str] = []
        for stop_time in nominal_stop_times:
            stop_id = self._normalize_stop_id_for_matching(stop_time.stop_id)
            if stop_id not in nominal_by_stop_id:
                nominal_by_stop_id[stop_id] = stop_time
                nominal_order.append(stop_id)

        unexpected_stop_added = False
        if treat_unexpected_stop_as_added_stop:
            for event in propagated_events:
                stop_id = self._normalize_stop_id_for_matching(event.get("stop_id"))
                if stop_id and stop_id not in nominal_by_stop_id:
                    event["schedule_relationship"] = "ADDED"
                    unexpected_stop_added = True
        else:
            propagated_events = [
                event for event in propagated_events if self._normalize_stop_id_for_matching(event.get("stop_id")) in nominal_by_stop_id
            ]

        realtime_stop_ids = {
            self._normalize_stop_id_for_matching(event.get("stop_id"))
            for event in propagated_events
            if event.get("stop_id")
        }

        missing_stop_added = False
        for stop_time in nominal_stop_times:
            nominal_stop_id = self._normalize_stop_id_for_matching(stop_time.stop_id)
            if nominal_stop_id in realtime_stop_ids:
                continue

            missing_stop_added = True
            propagated_events.append(
                {
                    "stop_id": str(stop_time.stop_id),
                    "stop_sequence": str(stop_time.stop_sequence),
                    "arrival_time": stop_time.arrival_time,
                    "departure_time": stop_time.departure_time,
                    "schedule_relationship": "SKIPPED" if treat_missing_stop_as_canceled_stop else "NO_DATA",
                    "is_valid": True,
                }
            )

        if not is_complete_stop_sequence:
            return propagated_events

        if not unexpected_stop_added and not missing_stop_added:
            def sort_key(event: dict[str, Any]) -> tuple[int, int, datetime, str]:
                stop_id = str(event.get("stop_id") or "")
                nominal_rank = nominal_order.index(stop_id) if stop_id in nominal_by_stop_id else len(nominal_order)
                departure_rank = self._coerce_stop_time_for_sort(
                    event.get("departure_time") or event.get("arrival_time")
                )
                return (
                    0 if stop_id in nominal_by_stop_id else 1,
                    nominal_rank,
                    departure_rank,
                    stop_id,
                )

            return sorted(propagated_events, key=sort_key)

        def sort_key(event: dict[str, Any]) -> tuple[int, int, datetime, str]:
            stop_id = str(event.get("stop_id") or "")
            departure_rank = self._coerce_stop_time_for_sort(
                event.get("departure_time") or event.get("arrival_time")
            )
            return (
                0 if stop_id in nominal_by_stop_id else 1,
                departure_rank,
                stop_id,
            )

        merged_events = sorted(propagated_events, key=sort_key)
        return merged_events

    @staticmethod
    def _extract_vehicle_trip_payload(record: dict[str, Any]) -> dict[str, Any]:
        """Normalize vehicle trip payload from flat or nested dialect shapes."""
        payload = record.get("trip", {})
        if not isinstance(payload, dict):
            payload = {}

        trip_id_value = record.get("trip_id") or payload.get("trip_id")
        if not trip_id_value:
            raise ValueError("Vehicle-position record is missing trip reference ('trip_id' or 'trip.trip_id')")

        return {
            "trip_id": str(trip_id_value),
            "start_time": str(record.get("trip_start_time") or payload.get("start_time") or ""),
            "start_date": str(record.get("trip_start_date") or payload.get("start_date") or ""),
            "route_id": str(record.get("trip_route_id") or payload.get("route_id") or ""),
            "schedule_relationship": str(
                record.get("trip_schedule_relationship")
                or payload.get("schedule_relationship")
                or "SCHEDULED"
            ),
            "assignment_type": str(
                record.get("trip_assignment_type")
                or payload.get("assignment_type")
                or "ASSIGNED"
            ),
            "is_active_on_create": bool(
                record.get("trip_is_active_on_create", payload.get("is_active", True))
            ),
            "is_valid": bool(record.get("trip_is_valid", payload.get("is_valid", True))),
        }
    
    async def sync_records(
        self, 
        repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
        source_id: int, 
        source_name: str,
        log_dumps: bool,
    ) -> dict[str, int]:
        """
        Synchronize records from the external data source to the database.
        
        This method orchestrates the generic sync process:
        1. Fetches dialect-defined records from the external source (via _fetch_records)
        2. Detects record type from fetched payload
        3. Dispatches to the corresponding record-type synchronizer
        
        Args:
            source_id: Database ID of the data source
            source_name: Name of the data source (for logging and deterministic IDs)
            
        Returns:
            Dictionary with keys 'added', 'updated', 'deleted' containing counts
        """
        adapter_type = self.get_adapter_type()
        logger.info(f"[{adapter_type}] Starting import from '{source_name}'")
        total_start = perf_counter()

        # Inject source_name and source_id into config so adapters can use them
        self.config["_source_name"] = source_name
        self.config["_source_id"] = source_id
        self.config["_log_dumps"] = bool(log_dumps)
        
        # Fetch records from external source.
        # Record shape and record type are defined by the selected dialect transformer.
        extract_start = perf_counter()
        fetched_payload = await self._fetch_records()
        extract_elapsed_ms = (perf_counter() - extract_start) * 1000
        transform_runtime_ms = fetched_payload.get("_transform_runtime_ms")
        if transform_runtime_ms is None:
            transform_start = perf_counter()
            record_type, records = self._normalize_fetched_payload(fetched_payload)
            transform_elapsed_ms = (perf_counter() - transform_start) * 1000
        else:
            record_type, records = self._normalize_fetched_payload(fetched_payload)
            transform_elapsed_ms = float(transform_runtime_ms)

        logger.info(
            f"[{adapter_type}] Fetched {len(records)} records from source "
            f"(record_type={record_type})"
        )

        load_start = perf_counter()
        try:
            async with self._realtime_sync_transaction(realtime_repository):
                if record_type == "service_alerts":
                    result = await self._sync_service_alert_records(
                        repository=repository,
                        realtime_repository=realtime_repository,
                        gtfs_repository=gtfs_repository,
                        source_id=source_id,
                        source_name=source_name,
                        records=records,
                    )
                elif record_type == "trip_updates":
                    result = await self._sync_trip_update_records(
                        repository=repository,
                        realtime_repository=realtime_repository,
                        gtfs_repository=gtfs_repository,
                        source_id=source_id,
                        source_name=source_name,
                        records=records,
                    )
                elif record_type == "vehicle_positions":
                    result = await self._sync_vehicle_position_records(
                        repository=repository,
                        realtime_repository=realtime_repository,
                        gtfs_repository=gtfs_repository,
                        source_id=source_id,
                        source_name=source_name,
                        records=records,
                    )
                else:
                    raise NotImplementedError(
                        f"Record type '{record_type}' is not supported by sync_records yet"
                    )
        finally:
            load_elapsed_ms = (perf_counter() - load_start) * 1000
            total_elapsed_ms = (perf_counter() - total_start) * 1000
            logger.info(
                "[%s] datasource run completed for '%s' (record_type=%s, total=%.2fms, extract=%.2fms, transform=%.2fms, load=%.2fms)",
                adapter_type,
                source_name,
                record_type,
                total_elapsed_ms,
                extract_elapsed_ms,
                transform_elapsed_ms,
                load_elapsed_ms,
            )

        return result

    @staticmethod
    @asynccontextmanager
    async def _realtime_sync_transaction(realtime_repository: RealtimeRepositoryInterface):
        """Use one realtime transaction when supported by the repository."""
        transaction = getattr(realtime_repository, "transaction", None)
        if transaction is None:
            yield
            return

        async with transaction():
            yield

    async def _sync_service_alert_records(
        self,
        repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
        source_id: int,
        source_name: str,
        records: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Synchronize service-alert records into the database."""
        policy = await repository.get_data_source_invalid_reference_policy(source_id)

        # Convert string to enum if needed (database stores as string)
        if isinstance(policy, str):
            policy = InvalidReferencePolicy(policy)

        logger.info(
            f"[{self.get_adapter_type()}] Synchronizing service-alert records from '{source_name}' "
            f"(policy: {policy.value})"
        )

        alert_dicts = records
        total_fetched = len(alert_dicts)

        # Load mappings and enrichments once per pipeline run.
        await self._identifier_mapping_service.initialize(repository, source_id)
        await self._entity_enrichment_service.initialize(repository, source_id)

        mapping_count = self._identifier_mapping_service.get_loaded_mapping_count()
        if mapping_count > 0:
            logger.info(
                f"[{self.get_adapter_type()}] Loaded {mapping_count} mapping entries"
            )
        
        # Apply enrichments before validation, as they may affect cause/effect/severity.
        enrichment_count = self._entity_enrichment_service.get_loaded_enrichment_count()
        if enrichment_count > 0:
            logger.info(
                f"[{self.get_adapter_type()}] Applying {enrichment_count} enrichment rules to records"
            )

            for alert_data in alert_dicts:
                await self._entity_enrichment_service.apply_enrichment_async(
                    alert_data,
                    self.get_adapter_type(),
                )
        
        # Load GTFS entities for validation
        gtfs_entities = await self._load_gtfs_entities(gtfs_repository)
        
        # Get IDs of alerts from the feed
        incoming_alert_ids = {alert_data["id"] for alert_data in alert_dicts}
        
        # Get existing alerts from this data source
        existing_alerts = {
            alert.id: alert
            for alert in await realtime_repository.list_service_alerts_for_data_source(source_id)
        }
        existing_alert_ids = set(existing_alerts.keys())
        
        # Also check if any incoming alerts exist in DB with different/null data_source_id
        # This handles migration scenarios and prevents duplicate key errors
        if incoming_alert_ids:
            alerts_by_id = {
                alert.id: alert
                for alert in await realtime_repository.list_service_alerts_by_ids(list(incoming_alert_ids))
            }
            
            # Merge into existing_alerts - alerts with matching IDs should be updated
            for alert_id, alert in alerts_by_id.items():
                if alert_id not in existing_alerts:
                    existing_alerts[alert_id] = alert
                    existing_alert_ids.add(alert_id)
        
        # Determine which alerts to add, update, or delete
        alerts_to_update = incoming_alert_ids & existing_alert_ids
        # Only delete alerts that belong to this data source
        alerts_to_delete = {
            aid for aid, alert in existing_alerts.items() 
            if alert.data_source_id == source_id and aid not in incoming_alert_ids
        }
        
        # Track alerts that should be deleted due to policy (will be added during processing)
        policy_based_deletes = set()
        
        # Statistics tracking
        stats_created = 0
        stats_created_inactive = 0
        stats_updated = 0
        stats_deleted = len(alerts_to_delete)
        stats_policy_discarded = 0
        
        # Delete alerts that are no longer in the feed
        if alerts_to_delete:
            await realtime_repository.delete_service_alerts_for_data_source_by_ids(
                source_id,
                list(alerts_to_delete),
            )
        
        # Process incoming alerts
        for alert_data in alert_dicts:
            alert_id = alert_data["id"]
            
            # Override source with data source name
            alert_data["source"] = source_name
            alert_data["data_source_id"] = source_id
            
            # Extract nested data
            translations_data = alert_data.pop("translations", [])
            periods_data = alert_data.pop("active_periods", [])
            entities_data = alert_data.pop("informed_entities", [])
            
            # Apply mappings to all entities and validate them
            # For DISCARD_INVALID_ELEMENTS policy, also clean individual fields
            validated_entities = []
            has_invalid_entity = False
            
            for entity_data in entities_data:
                # Apply mappings to entity data
                mapped_entity_data = await self._identifier_mapping_service.apply_mapping_async(
                    entity_data,
                )
                
                # For DISCARD_INVALID_ELEMENTS policy, validate and clean individual fields
                if policy == InvalidReferencePolicy.DISCARD_INVALID_ELEMENTS:
                    cleaned_entity, has_valid_ref = await self._run_cpu_bound(
                        self._validate_and_clean_entity_elements,
                        mapped_entity_data,
                        gtfs_entities,
                    )
                    
                    # Mark as valid if at least one reference is valid
                    # Unless already explicitly marked as invalid (e.g., trip references)
                    if "is_valid" not in mapped_entity_data:
                        cleaned_entity["is_valid"] = has_valid_ref
                    else:
                        cleaned_entity["is_valid"] = mapped_entity_data["is_valid"]
                    
                    if not cleaned_entity["is_valid"]:
                        has_invalid_entity = True
                        logger.debug(
                            f"[{self.get_adapter_type()}] Entity has no valid references in alert {alert_id}: "
                            f"{mapped_entity_data}"
                        )
                    
                    validated_entities.append(cleaned_entity)
                else:
                    # Standard validation for other policies
                    # Check if entity already has is_valid flag set (e.g., trip references)
                    if "is_valid" in mapped_entity_data:
                        is_valid = mapped_entity_data["is_valid"]
                    else:
                        is_valid = await self._run_cpu_bound(
                            self._validate_entity,
                            mapped_entity_data,
                            gtfs_entities,
                        )
                        # Mark entity as valid/invalid
                        mapped_entity_data["is_valid"] = is_valid
                    
                    if not is_valid:
                        has_invalid_entity = True
                        logger.debug(
                            f"[{self.get_adapter_type()}] Invalid entity reference in alert {alert_id}: "
                            f"{mapped_entity_data}"
                        )
                    
                    validated_entities.append(mapped_entity_data)
            
            # Apply invalid reference policy
            should_skip_alert = False
            should_deactivate_alert = False
            entities_to_create = validated_entities
            
            if has_invalid_entity:
                if policy == InvalidReferencePolicy.DISCARD_ENTIRE_OBJECT:
                    # Discard entire alert if any reference is invalid
                    logger.debug(
                        f"[{self.get_adapter_type()}] Discarding alert {alert_id} "
                        f"due to invalid references (policy: {policy.value})"
                    )
                    should_skip_alert = True
                    stats_policy_discarded += 1
                    
                    # If the alert already exists, mark it for deletion
                    if alert_id in existing_alert_ids:
                        policy_based_deletes.add(alert_id)
                
                elif policy == InvalidReferencePolicy.DISCARD_INVALID:
                    # Keep only valid entities
                    entities_to_create = [e for e in validated_entities if e["is_valid"]]
                    
                    # If no valid entities remain, deactivate the alert
                    if not entities_to_create:
                        should_deactivate_alert = True
                        logger.debug(
                            f"[{self.get_adapter_type()}] Deactivating alert {alert_id} "
                            f"- all entity references were invalid (policy: {policy.value})"
                        )
                    else:
                        logger.debug(
                            f"[{self.get_adapter_type()}] Removed {len(validated_entities) - len(entities_to_create)} "
                            f"invalid entities from alert {alert_id} (policy: {policy.value})"
                        )
                
                elif policy == InvalidReferencePolicy.DISCARD_INVALID_ELEMENTS:
                    # Keep only entities that have at least one valid reference
                    # (invalid fields within entities have already been cleaned)
                    entities_to_create = [e for e in validated_entities if e["is_valid"]]
                    
                    # If no valid entities remain, deactivate the alert
                    if not entities_to_create:
                        should_deactivate_alert = True
                        logger.debug(
                            f"[{self.get_adapter_type()}] Deactivating alert {alert_id} "
                            f"- all entities had only invalid references (policy: {policy.value})"
                        )
                    else:
                        logger.debug(
                            f"[{self.get_adapter_type()}] Cleaned {len(validated_entities) - len(entities_to_create)} "
                            f"entities with no valid references from alert {alert_id} (policy: {policy.value})"
                        )
                
                elif policy == InvalidReferencePolicy.KEEP_OBJECT_DISABLED:
                    # Keep all entities but deactivate the alert
                    should_deactivate_alert = True
                    logger.debug(
                        f"[{self.get_adapter_type()}] Deactivating alert {alert_id} "
                        f"due to invalid references (policy: {policy.value})"
                    )
                
                # policy == InvalidReferencePolicy.NOT_SPECIFIED:
                # Pass through without changes
            
            # Deduplicate entities - remove duplicates that may have been created
            # through mapping or policy application
            if entities_to_create:
                original_count = len(entities_to_create)
                entities_to_create = await self._run_cpu_bound(
                    self._deduplicate_entities,
                    entities_to_create,
                )
                duplicates_removed = original_count - len(entities_to_create)
                
                if duplicates_removed > 0:
                    logger.debug(
                        f"[{self.get_adapter_type()}] Removed {duplicates_removed} duplicate "
                        f"entities from alert {alert_id}"
                    )
            
            # Check if alert has no entities at all (either none provided or all removed by policy)
            # Deactivate such alerts as they have no meaningful content
            if not entities_to_create and not should_skip_alert:
                should_deactivate_alert = True
                logger.debug(
                    f"[{self.get_adapter_type()}] Deactivating alert {alert_id} - no valid entities"
                )
            
            # Skip this alert if policy dictates
            if should_skip_alert:
                continue
            
            if alert_id in alerts_to_update:
                logger.debug(f"[{self.get_adapter_type()}] Updating alert {alert_id}")
                stats_updated += 1
                await realtime_repository.upsert_service_alert_from_sync(
                    alert_id=alert_id,
                    source_id=source_id,
                    source_name=source_name,
                    cause=alert_data["cause"],
                    effect=alert_data["effect"],
                    severity_level=alert_data["severity_level"],
                    is_active_on_create=False,
                    translations=translations_data,
                    active_periods=periods_data,
                    informed_entities=entities_to_create,
                )
            else:
                # INSERT new alert
                logger.debug(f"[{self.get_adapter_type()}] Creating new alert {alert_id}")
                
                # Set is_active based on policy
                if should_deactivate_alert:
                    alert_data["is_active"] = False
                    stats_created_inactive += 1
                
                stats_created += 1

                await realtime_repository.upsert_service_alert_from_sync(
                    alert_id=alert_id,
                    source_id=source_id,
                    source_name=source_name,
                    cause=alert_data["cause"],
                    effect=alert_data["effect"],
                    severity_level=alert_data["severity_level"],
                    is_active_on_create=alert_data.get("is_active", True),
                    translations=translations_data,
                    active_periods=periods_data,
                    informed_entities=entities_to_create,
                )
        
        # Delete alerts that were discarded due to policy
        if policy_based_deletes:
            logger.debug(
                f"[{self.get_adapter_type()}] Deleting {len(policy_based_deletes)} existing alerts "
                f"due to invalid reference policy"
            )

            await realtime_repository.delete_service_alerts_by_ids(list(policy_based_deletes))

            # Add to total delete count
            stats_deleted += len(policy_based_deletes)
        
        # Log final statistics
        logger.info(
            f"[{self.get_adapter_type()}] Import completed for '{source_name}': "
            f"fetched={total_fetched}, created={stats_created} "
            f"(inactive={stats_created_inactive}), updated={stats_updated}, "
            f"deleted={stats_deleted}, policy_discarded={stats_policy_discarded}"
        )
        
        return {
            "added": stats_created,
            "updated": stats_updated,
            "deleted": stats_deleted,
        }

    async def _sync_trip_update_records(
        self,
        repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
        source_id: int,
        source_name: str,
        records: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Synchronize trip-update records into the database."""
        policy = await repository.get_data_source_invalid_reference_policy(source_id)
        if isinstance(policy, str):
            policy = InvalidReferencePolicy(policy)

        logger.info(
            f"[{self.get_adapter_type()}] Synchronizing trip-update records from '{source_name}' "
            f"(policy: {policy.value})"
        )

        await self._identifier_mapping_service.initialize(repository, source_id)

        mapping_count = self._identifier_mapping_service.get_loaded_mapping_count()
        if mapping_count > 0:
            logger.info(
                f"[{self.get_adapter_type()}] Loaded {mapping_count} mapping entries"
            )

        treat_unexpected_stop_as_added_stop = bool(
            self.config.get("treat_unexpected_stop_as_added_stop", False)
        )
        
        treat_missing_stop_as_canceled_stop = bool(
            self.config.get("treat_missing_stop_as_canceled_stop", False)
        )

        gtfs_entities = await self._load_gtfs_entities(gtfs_repository)
        nominal_trip_ids = gtfs_entities.get("trip", set())
        if self._matching_service is None:
            self._matching_service = MatchingService(gtfs_repository, get_caching_service())

        existing_trips = {
            trip.id: trip
            for trip in await realtime_repository.list_trips_for_data_source(source_id)
        }

        existing_trip_ids = set(existing_trips.keys())

        incoming_trip_reference_ids = {
            str(record.get("trip_id") or "")
            for record in records
            if record.get("trip_id")
        }

        existing_trip_uuid_by_trip_id = {
            str(trip.trip_id): trip.id
            for trip in await realtime_repository.list_trips_by_trip_ids(
                list(incoming_trip_reference_ids)
            )
        }

        incoming_trip_ids = {
            existing_trip_uuid_by_trip_id.get(
                str(record.get("trip_id") or ""),
                self._record_uuid(record, source_name, fallback_key="trip_id", kind="Trip-update"),
            )
            for record in records
        }

        existing_trip_ids.update(existing_trip_uuid_by_trip_id.values())

        if incoming_trip_ids:
            trips_by_id = {
                trip.id: trip
                for trip in await realtime_repository.list_trips_by_ids(list(incoming_trip_ids))
            }

            for trip_id, trip in trips_by_id.items():
                if trip_id not in existing_trips:
                    existing_trips[trip_id] = trip
                    existing_trip_ids.add(trip_id)

        trips_to_delete = {
            trip_id for trip_id, trip in existing_trips.items()
            if trip.data_source_id == source_id and trip_id not in incoming_trip_ids
        }

        stats_created = 0
        stats_updated = 0
        stats_deleted = len(trips_to_delete)
        policy_based_deletes: set[uuid.UUID] = set()

        if trips_to_delete:
            await realtime_repository.delete_trips_for_data_source_by_ids(
                source_id,
                list(trips_to_delete),
            )

        for record in records:
            is_complete_stop_sequence = bool(record.get("is_complete_stop_sequence", False))
            schedule_relationship = str(record.get("schedule_relationship", "SCHEDULED") or "SCHEDULED").upper()

            mapped_trip = await self._identifier_mapping_service.apply_mapping_async(
                {
                    "route_id": record.get("route_id"),
                }
            )
            mapped_route_id = str(mapped_trip.get("route_id") or "")
            route_is_valid = bool(mapped_route_id) and mapped_route_id in gtfs_entities.get("route", set())
            is_new_trip = schedule_relationship == "NEW"

            stop_events = []
            has_invalid_stop_reference = False
            for event in record.get("stop_events", []):
                mapped_event = dict(event)
                mapped_stop = await self._identifier_mapping_service.apply_mapping_async(
                    {
                        "stop_id": mapped_event.get("stop_id"),
                    }
                )
                mapped_event["stop_id"] = mapped_stop.get("stop_id")

                mapped_stop_id = str(mapped_event.get("stop_id") or "")
                stop_is_valid = bool(mapped_stop_id) and mapped_stop_id in gtfs_entities.get("stop", set())
                if not stop_is_valid:
                    has_invalid_stop_reference = True

                mapped_event["is_valid"] = bool(mapped_event.get("is_valid", True)) and stop_is_valid
                stop_events.append(mapped_event)

            derived_trip_id = str(record["trip_id"])
            original_trip_id = derived_trip_id
            resolved_trip_id = derived_trip_id
            assignment_type = AssignmentType.DIRECT_BY_ID.value
            trip_reference_is_valid = True if is_new_trip else derived_trip_id in nominal_trip_ids

            mapped_match_start_stop = await self._identifier_mapping_service.apply_mapping_async(
                {
                    "stop_id": record.get("scheduled_start_stop_id"),
                }
            )
            mapped_match_end_stop = await self._identifier_mapping_service.apply_mapping_async(
                {
                    "stop_id": record.get("scheduled_end_stop_id"),
                }
            )

            scheduled_start_time = self._coerce_datetime(record.get("scheduled_start_time"))
            scheduled_end_time = self._coerce_datetime(record.get("scheduled_end_time"))
            scheduled_start_stop_id = mapped_match_start_stop.get("stop_id")
            scheduled_end_stop_id = mapped_match_end_stop.get("stop_id")
            scheduled_intermediate_stops: list[tuple[str, datetime]] = []

            intermediate_candidates = record.get("scheduled_intermediate_stops")
            if isinstance(intermediate_candidates, list):
                for candidate in intermediate_candidates:
                    if not isinstance(candidate, tuple) or len(candidate) != 2:
                        continue

                    candidate_stop_id, candidate_time = candidate
                    mapped_intermediate_stop = await self._identifier_mapping_service.apply_mapping_async(
                        {
                            "stop_id": candidate_stop_id,
                        }
                    )
                    mapped_stop_id = mapped_intermediate_stop.get("stop_id")
                    coerced_time = self._coerce_datetime(candidate_time)

                    if mapped_stop_id is None or coerced_time is None:
                        continue

                    scheduled_intermediate_stops.append((str(mapped_stop_id), coerced_time))

            if not is_new_trip and not trip_reference_is_valid:
                matched_trip_id = await self._matching_service.match(
                    trip_id=derived_trip_id,
                    route_id=str(mapped_trip.get("route_id") or "") or None,
                    operation_day_date=self._parse_operation_day(record.get("start_date")),
                    scheduled_start_time=scheduled_start_time,
                    scheduled_end_time=scheduled_end_time,
                    scheduled_start_stop_id=(
                        str(scheduled_start_stop_id)
                        if scheduled_start_stop_id is not None
                        else None
                    ),
                    scheduled_end_stop_id=(
                        str(scheduled_end_stop_id)
                        if scheduled_end_stop_id is not None
                        else None
                    ),
                    scheduled_intermediate_stops=scheduled_intermediate_stops,
                )

                if matched_trip_id is not None:
                    resolved_trip_id = matched_trip_id
                    assignment_type = AssignmentType.MATCHED_BY_START_STOP.value
                    trip_reference_is_valid = True
                    
                    await realtime_repository.delete_trips_by_trip_ids([original_trip_id])
                else:
                    assignment_type = AssignmentType.NO_MATCH_GENERAL.value

            persisted_trip_uuid = existing_trip_uuid_by_trip_id.get(str(resolved_trip_id))
            if persisted_trip_uuid is None:
                persisted_trip_uuid = self._make_unique_id(resolved_trip_id, source_name)

            existing_trip = persisted_trip_uuid in existing_trip_ids

            if not is_new_trip:
                nominal_trip = await gtfs_repository.get_gtfs_trip_with_stop_times(resolved_trip_id)
                nominal_stop_times = list(nominal_trip.stop_times) if nominal_trip is not None else []
                stop_events = await self._run_cpu_bound(
                    self._propagate_trip_update_stop_events,
                    stop_events,
                    nominal_stop_times,
                    treat_unexpected_stop_as_added_stop=treat_unexpected_stop_as_added_stop,
                    treat_missing_stop_as_canceled_stop=treat_missing_stop_as_canceled_stop,
                    is_complete_stop_sequence=is_complete_stop_sequence,
                )

                if is_complete_stop_sequence:
                    for idx, event in enumerate(stop_events, start=1):
                        event["stop_sequence"] = str(idx)

            has_invalid_stop_reference = any(not bool(event.get("is_valid", True)) for event in stop_events)

            has_invalid_reference = (not route_is_valid) or has_invalid_stop_reference or (not trip_reference_is_valid)

            should_skip_trip = False
            should_deactivate_trip = False
            stop_events_to_persist = stop_events
            route_id_to_persist = mapped_route_id

            if has_invalid_reference:
                if policy == InvalidReferencePolicy.DISCARD_ENTIRE_OBJECT:
                    should_skip_trip = True
                    if persisted_trip_uuid in existing_trip_ids:
                        policy_based_deletes.add(persisted_trip_uuid)

                elif policy in (
                    InvalidReferencePolicy.DISCARD_INVALID,
                    InvalidReferencePolicy.DISCARD_INVALID_ELEMENTS,
                ):
                    stop_events_to_persist = [event for event in stop_events if bool(event.get("is_valid"))]
                    if not route_is_valid:
                        route_id_to_persist = ""

                    has_any_valid_reference = (
                        trip_reference_is_valid
                        or bool(route_id_to_persist)
                        or bool(stop_events_to_persist)
                    )
                    if (
                        not existing_trip
                        and ((not trip_reference_is_valid) or (not has_any_valid_reference))
                    ):
                        should_deactivate_trip = True

                elif policy == InvalidReferencePolicy.KEEP_OBJECT_DISABLED:
                    should_deactivate_trip = not existing_trip

            if should_skip_trip:
                continue

            if existing_trip:
                is_active_on_create = bool(existing_trips[persisted_trip_uuid].is_active)
            else:
                is_active_on_create = bool(record.get("is_active", True))
                if should_deactivate_trip:
                    is_active_on_create = False

            trip_is_valid = (
                bool(record.get("is_valid", True))
                and route_is_valid
                and trip_reference_is_valid
                and not has_invalid_stop_reference
            )

            if existing_trip:
                stats_updated += 1
            else:
                stats_created += 1
                existing_trip_ids.add(persisted_trip_uuid)

            existing_trip_uuid_by_trip_id[str(resolved_trip_id)] = persisted_trip_uuid

            await realtime_repository.update_trip_update_from_sync(
                trip_uuid=persisted_trip_uuid,
                source_id=source_id,
                source_name=source_name,
                trip_id=resolved_trip_id,
                start_time=str(record["start_time"]),
                start_date=str(record["start_date"]),
                route_id=route_id_to_persist,
                schedule_relationship=str(record.get("schedule_relationship", "SCHEDULED")),
                assignment_type=assignment_type,
                is_active_on_create=is_active_on_create,
                is_valid=trip_is_valid,
                stop_events=stop_events_to_persist,
                original_trip_id=original_trip_id,
                scheduled_start_stop_id=(
                    str(scheduled_start_stop_id)
                    if scheduled_start_stop_id is not None
                    else None
                ),
                scheduled_end_stop_id=(
                    str(scheduled_end_stop_id)
                    if scheduled_end_stop_id is not None
                    else None
                ),
                scheduled_start_time=scheduled_start_time,
                scheduled_end_time=scheduled_end_time,
            )

        if policy_based_deletes:
            await realtime_repository.delete_trips_for_data_source_by_ids(
                source_id,
                list(policy_based_deletes),
            )
            stats_deleted += len(policy_based_deletes)

        logger.info(
            f"[{self.get_adapter_type()}] Trip-update import completed for '{source_name}': "
            f"fetched={len(records)}, created={stats_created}, updated={stats_updated}, deleted={stats_deleted}"
        )

        return {
            "added": stats_created,
            "updated": stats_updated,
            "deleted": stats_deleted,
        }

    async def _sync_vehicle_position_records(
        self,
        repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
        source_id: int,
        source_name: str,
        records: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Synchronize vehicle-position records into the database."""
        policy = await repository.get_data_source_invalid_reference_policy(source_id)
        if isinstance(policy, str):
            policy = InvalidReferencePolicy(policy)

        logger.info(
            f"[{self.get_adapter_type()}] Synchronizing vehicle-position records from '{source_name}' "
            f"(policy: {policy.value})"
        )

        await self._identifier_mapping_service.initialize(repository, source_id)

        mapping_count = self._identifier_mapping_service.get_loaded_mapping_count()
        if mapping_count > 0:
            logger.info(
                f"[{self.get_adapter_type()}] Loaded {mapping_count} mapping entries"
            )

        gtfs_entities = await self._load_gtfs_entities(gtfs_repository)
        nominal_trip_ids = gtfs_entities.get("trip", set())
        if self._matching_service is None:
            self._matching_service = MatchingService(gtfs_repository, get_caching_service())

        incoming_vehicle_ids = {
            self._record_uuid(record, source_name, fallback_key="vehicle_id", kind="Vehicle-position")
            for record in records
        }

        incoming_vehicle_trip_ids: set[str] = set()
        for record in records:
            try:
                vehicle_trip_payload = self._extract_vehicle_trip_payload(record)
            except ValueError:
                continue

            incoming_vehicle_trip_ids.add(str(vehicle_trip_payload.get("trip_id") or ""))

        incoming_vehicle_trip_ids.discard("")

        existing_trip_uuid_by_trip_id = {
            str(trip.trip_id): trip.id
            for trip in await realtime_repository.list_trips_by_trip_ids(list(incoming_vehicle_trip_ids))
        }

        existing_vehicles = {
            vehicle.id: vehicle
            for vehicle in await realtime_repository.list_vehicles_for_data_source(source_id)
        }
        existing_vehicle_ids = set(existing_vehicles.keys())
        vehicle_uuid_by_trip_id = {
            str(vehicle.trip_id): vehicle.id
            for vehicle in existing_vehicles.values()
            if getattr(vehicle, "trip_id", None)
        }
        processed_vehicle_ids = set(existing_vehicle_ids)

        if incoming_vehicle_ids:
            vehicles_by_id = {
                vehicle.id: vehicle
                for vehicle in await realtime_repository.list_vehicles_by_ids(list(incoming_vehicle_ids))
            }
            
            for vehicle_id, vehicle in vehicles_by_id.items():
                if vehicle_id not in existing_vehicles:
                    existing_vehicles[vehicle_id] = vehicle
                    existing_vehicle_ids.add(vehicle_id)

        vehicles_to_update = incoming_vehicle_ids & existing_vehicle_ids
        vehicles_to_delete = {
            vehicle_id for vehicle_id, vehicle in existing_vehicles.items()
            if vehicle.data_source_id == source_id and vehicle_id not in incoming_vehicle_ids
        }

        stats_created = 0
        stats_updated = 0
        stats_deleted = len(vehicles_to_delete)
        policy_based_deletes: set[uuid.UUID] = set()

        if vehicles_to_delete:
            await realtime_repository.delete_vehicles_for_data_source_by_ids(
                source_id,
                list(vehicles_to_delete),
            )

        deleted_vehicle_ids: set[uuid.UUID] = set(vehicles_to_delete)

        for record in records:
            vehicle_uuid = self._record_uuid(record, source_name, fallback_key="vehicle_id", kind="Vehicle-position")
            try:
                trip_payload = self._extract_vehicle_trip_payload(record)
            except ValueError as exc:
                logger.debug(
                    f"[{self.get_adapter_type()}] Discarding vehicle-position record due to invalid trip payload: {exc}"
                )
                
                continue

            mapped_trip = await self._identifier_mapping_service.apply_mapping_async(
                {
                    "route_id": trip_payload.get("route_id"),
                }
            )
            trip_payload["route_id"] = str(mapped_trip.get("route_id") or "")
            route_is_valid = bool(trip_payload["route_id"]) and trip_payload["route_id"] in gtfs_entities.get("route", set())

            stop_reference_value = record.get("stop_id")
            stop_reference_is_valid = True
            if stop_reference_value:
                stop_reference_is_valid = str(stop_reference_value) in gtfs_entities.get("stop", set())

            derived_trip_id = trip_payload["trip_id"]
            resolved_trip_id = derived_trip_id
            trip_assignment_type = AssignmentType.DIRECT_BY_ID.value
            vehicle_assignment_type = AssignmentType.DIRECT_BY_ID.value
            trip_reference_is_valid = derived_trip_id in nominal_trip_ids

            if not trip_reference_is_valid:
                mapped_match_start_stop = await self._identifier_mapping_service.apply_mapping_async(
                    {
                        "stop_id": record.get("scheduled_start_stop_id"),
                    }
                )
                mapped_match_end_stop = await self._identifier_mapping_service.apply_mapping_async(
                    {
                        "stop_id": record.get("scheduled_end_stop_id"),
                    }
                )
    
                scheduled_start_time = self._coerce_datetime(record.get("scheduled_start_time"))
                scheduled_end_time = self._coerce_datetime(record.get("scheduled_end_time"))
                scheduled_start_stop_id = mapped_match_start_stop.get("stop_id")
                scheduled_end_stop_id = mapped_match_end_stop.get("stop_id")
                scheduled_intermediate_stops: list[tuple[str, datetime]] = []
    
                intermediate_candidates = trip_payload.get("scheduled_intermediate_stops")
                if isinstance(intermediate_candidates, list):
                    for candidate in intermediate_candidates:
                        if not isinstance(candidate, tuple) or len(candidate) != 2:
                            continue
    
                        candidate_stop_id, candidate_time = candidate
                        mapped_intermediate_stop = await self._identifier_mapping_service.apply_mapping_async(
                            {
                                "stop_id": candidate_stop_id,
                            }
                        )
                        
                        mapped_stop_id = mapped_intermediate_stop.get("stop_id")
                        coerced_time = self._coerce_datetime(candidate_time)
    
                        if mapped_stop_id is None or coerced_time is None:
                            continue
    
                        scheduled_intermediate_stops.append((str(mapped_stop_id), coerced_time))

                matched_trip_id = await self._matching_service.match(
                    trip_id=derived_trip_id,
                    route_id=trip_payload["route_id"] or None,
                    operation_day_date=self._parse_operation_day(trip_payload.get("start_date")),
                    scheduled_start_time=scheduled_start_time,
                    scheduled_end_time=scheduled_end_time,
                    scheduled_start_stop_id=(
                        str(scheduled_start_stop_id)
                        if scheduled_start_stop_id is not None
                        else None
                    ),
                    scheduled_end_stop_id=(
                        str(scheduled_end_stop_id)
                        if scheduled_end_stop_id is not None
                        else None
                    ),
                    scheduled_intermediate_stops=scheduled_intermediate_stops,
                )

                if matched_trip_id is not None:
                    resolved_trip_id = matched_trip_id
                    trip_assignment_type = AssignmentType.MATCHED_BY_CURRENT_STOP.value
                    vehicle_assignment_type = AssignmentType.MATCHED_BY_CURRENT_STOP.value
                    trip_reference_is_valid = True
                    await realtime_repository.delete_trips_by_trip_ids([derived_trip_id])
                else:
                    trip_assignment_type = AssignmentType.NO_MATCH_GENERAL.value
                    vehicle_assignment_type = AssignmentType.NO_MATCH_GENERAL.value
                    trip_payload["is_active_on_create"] = False

            has_invalid_reference = (not route_is_valid) or (not stop_reference_is_valid) or (not trip_reference_is_valid)

            should_skip_vehicle = False
            should_deactivate_vehicle = False

            if has_invalid_reference:
                if policy == InvalidReferencePolicy.DISCARD_ENTIRE_OBJECT:
                    should_skip_vehicle = True
                    if vehicle_uuid in existing_vehicle_ids:
                        policy_based_deletes.add(vehicle_uuid)

                elif policy in (
                    InvalidReferencePolicy.DISCARD_INVALID,
                    InvalidReferencePolicy.DISCARD_INVALID_ELEMENTS,
                ):
                    if not route_is_valid:
                        trip_payload["route_id"] = ""

                    has_any_valid_reference = (
                        trip_reference_is_valid
                        or bool(trip_payload["route_id"])
                        or stop_reference_is_valid
                    )
                    if (not trip_reference_is_valid) or (not has_any_valid_reference):
                        should_deactivate_vehicle = True

                elif policy == InvalidReferencePolicy.KEEP_OBJECT_DISABLED:
                    should_deactivate_vehicle = True

            if should_skip_vehicle:
                continue

            vehicle_is_active_on_create = bool(record.get("is_active", True))
            if should_deactivate_vehicle:
                vehicle_is_active_on_create = False

            trip_is_valid = bool(trip_payload.get("is_valid", True)) and route_is_valid and trip_reference_is_valid
            vehicle_is_valid = (
                bool(record.get("is_valid", True))
                and route_is_valid
                and stop_reference_is_valid
                and trip_reference_is_valid
            )

            trip_payload["trip_id"] = resolved_trip_id
            trip_id_key = str(trip_payload["trip_id"])

            vehicle_uuid = vehicle_uuid_by_trip_id.get(trip_id_key)
            if vehicle_uuid is None:
                vehicle_uuid = self._record_uuid(
                    record,
                    source_name,
                    fallback_key="vehicle_id",
                    kind="Vehicle-position",
                )
                vehicle_uuid_by_trip_id[trip_id_key] = vehicle_uuid

            existing_trip_uuid = existing_trip_uuid_by_trip_id.get(str(resolved_trip_id))
            if existing_trip_uuid is not None:
                trip_uuid = existing_trip_uuid
            else:
                trip_uuid = self._make_unique_id(trip_payload["trip_id"], source_name)
                existing_trip_uuid_by_trip_id[str(resolved_trip_id)] = trip_uuid

            if vehicle_uuid in processed_vehicle_ids:
                stats_updated += 1
            else:
                stats_created += 1
                processed_vehicle_ids.add(vehicle_uuid)

            current_stop_sequence_raw = record.get("current_stop_sequence")
            try:
                current_stop_sequence = (
                    int(current_stop_sequence_raw)
                    if current_stop_sequence_raw is not None
                    else None
                )
            except (TypeError, ValueError):
                current_stop_sequence = None

            await realtime_repository.update_vehicle_position_from_sync(
                vehicle_uuid=vehicle_uuid,
                source_id=source_id,
                source_name=source_name,
                trip_uuid=trip_uuid,
                trip_id=trip_payload["trip_id"],
                trip_start_time=trip_payload["start_time"],
                trip_start_date=trip_payload["start_date"],
                trip_route_id=trip_payload["route_id"],
                trip_schedule_relationship=trip_payload["schedule_relationship"],
                trip_assignment_type=trip_assignment_type,
                trip_is_active_on_create=trip_payload["is_active_on_create"],
                trip_is_valid=trip_is_valid,
                vehicle_id=str(record["vehicle_id"]),
                vehicle_label=record.get("vehicle_label"),
                vehicle_license_plate=record.get("vehicle_license_plate"),
                vehicle_wheelchair_accessible=str(record.get("vehicle_wheelchair_accessible", "NO_VALUE")),
                timestamp=record["timestamp"],
                latitude=float(record["latitude"]),
                longitude=float(record["longitude"]),
                current_stop_sequence=current_stop_sequence,
                current_status=str(record.get("current_status", "IN_TRANSIT_TO")),
                assignment_type=vehicle_assignment_type,
                congestion_level=str(record.get("congestion_level", "UNKNOWN_CONGESTION_LEVEL")),
                is_active_on_create=vehicle_is_active_on_create,
                is_valid=vehicle_is_valid,
            )

        if policy_based_deletes:
            await realtime_repository.delete_vehicles_for_data_source_by_ids(
                source_id,
                list(policy_based_deletes),
            )
            stats_deleted += len(policy_based_deletes)
            deleted_vehicle_ids.update(policy_based_deletes)

        deleted_vehicle_trip_ids = {
            str(existing_vehicles[vehicle_id].trip_id)
            for vehicle_id in deleted_vehicle_ids
            if vehicle_id in existing_vehicles and getattr(existing_vehicles[vehicle_id], "trip_id", None)
        }

        if deleted_vehicle_trip_ids:
            trip_ids_with_stop_events = await realtime_repository.list_trip_ids_with_stop_events(
                list(deleted_vehicle_trip_ids)
            )

            deletable_trip_ids = deleted_vehicle_trip_ids - trip_ids_with_stop_events

            if deletable_trip_ids:
                deletable_trips = await realtime_repository.list_trips_by_trip_ids(
                    list(deletable_trip_ids)
                )
                
                deletable_trip_uuids = [
                    trip.id
                    for trip in deletable_trips
                    if trip.data_source_id == source_id
                ]

                if deletable_trip_uuids:
                    await realtime_repository.delete_trips_for_data_source_by_ids(
                        source_id,
                        deletable_trip_uuids,
                    )

        logger.info(
            f"[{self.get_adapter_type()}] Vehicle-position import completed for '{source_name}': "
            f"fetched={len(records)}, created={stats_created}, updated={stats_updated}, deleted={stats_deleted}"
        )

        return {
            "added": stats_created,
            "updated": stats_updated,
            "deleted": stats_deleted,
        }

