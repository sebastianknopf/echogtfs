"""Base datasource implementation for external data feeds."""

from abc import abstractmethod
import asyncio
from collections.abc import Awaitable, Callable
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from time import perf_counter
from typing import Any

from echogtfs.datasources.intf_datasource import DatasourceInterface
from echogtfs.services.mapping.intf_identifier_mapping import IdentifierMappingInterface
from echogtfs.services.caching.intf_caching_service import CachingServiceInterface
from echogtfs.services.matching.intf_matching_service import MatchingServiceInterface
from echogtfs.services.caching import get_caching_service
from echogtfs.services.database import get_system_repository
from echogtfs.services.datalog import DatalogService
from echogtfs.services.realtimeprocessing import RealtimeProcessingDispatcherService
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
        self._caching_service: CachingServiceInterface = get_caching_service()
        self._validate_config()

    def get_filters(self) -> dict[str, list[str]]:
        """Return configured filters grouped by their known prefixes."""
        filters = {"line": [], "operator": [], "legacy": []}
        configured_filter = self.config.get("filter", "")

        if not configured_filter:
            return filters

        for filter_value in re.split(r"[,\s]+", configured_filter.strip()):
            filter_value = filter_value.strip()
            
            matched_prefix = False
            for filter_type in ("line", "operator"):
                prefix = f"{filter_type}/"
                if filter_value.startswith(prefix):
                    value = filter_value[len(prefix):].strip()
                    if value:
                        filters[filter_type].append(value)
                    
                    matched_prefix = True
                    break

            if not matched_prefix and filter_value:
                filters["legacy"].append(filter_value)

        return filters
    
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

    def _is_event_based_execution(self) -> bool:
        """Return True when the owning data source only runs via the push API.

        Polling-only config fields (e.g. endpoint) are not required in that case.
        """
        return self.config.get("_execution_type") == "event_based"
    
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

    async def _run_cpu_bound(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run CPU-bound synchronous datasource work in a worker thread."""
        return await asyncio.to_thread(func, *args, **kwargs)

    async def _parse_and_log_xml_payload(self, payload: bytes, content_type: str | None) -> ET.Element:
        """Decode, log, and parse an XML payload provided directly by the push API."""
        adapter_type = self.get_adapter_type()
        self.config["_adapter_type"] = adapter_type
        request_headers = {"Content-Type": content_type} if content_type else None

        try:
            xml_content = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.error(f"[{adapter_type}] Failed to decode pushed payload: {exc}")
            
            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url="",
                request_headers=request_headers,
                response_headers=None,
                response_status_code=422,
                response_content=str(exc),
                response_content_type="text/plain",
            )

            raise ValueError(f"Failed to decode pushed {adapter_type} payload: {exc}") from exc

        await self._log_request(
            source_id=self.config.get("_source_id"),
            request_url="",
            request_headers=request_headers,
            response_headers=None,
            response_status_code=200,
            response_content=xml_content,
            response_content_type="application/xml",
        )

        try:
            return await self._run_cpu_bound(ET.fromstring, xml_content)
        except ET.ParseError as exc:
            logger.error(f"[{adapter_type}] Failed to parse pushed XML: {exc}")
            
            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url="",
                request_headers=request_headers,
                response_headers=None,
                response_status_code=500,
                response_content=str(exc),
                response_content_type="text/plain",
            )

            raise ValueError(f"Failed to parse pushed {adapter_type} XML: {exc}") from exc

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
        # Inject source_name and source_id into config so adapters can use them
        self.config["_source_name"] = source_name
        self.config["_source_id"] = source_id
        self.config["_log_dumps"] = bool(log_dumps)

        return await self._sync_from_fetch(
            self._fetch_records,
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=source_id,
            source_name=source_name,
        )

    async def sync_records_from_payload(
        self,
        payload: bytes,
        content_type: str | None,
        repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
        source_id: int,
        source_name: str,
        log_dumps: bool,
    ) -> dict[str, int]:
        """Synchronize records from an already-provided payload (push API)."""
        self.config["_source_name"] = source_name
        self.config["_source_id"] = source_id
        self.config["_log_dumps"] = bool(log_dumps)

        async def _fetch() -> dict[str, Any]:
            return await self._fetch_records_from_payload(payload, content_type)

        return await self._sync_from_fetch(
            _fetch,
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=source_id,
            source_name=source_name,
        )

    async def _sync_from_fetch(
        self, fetch_callable: Callable[[], Awaitable[dict[str, Any]]], *, repository: SystemRepositoryInterface, realtime_repository: RealtimeRepositoryInterface, gtfs_repository: GtfsRepositoryInterface, source_id: int, source_name: str,
    ) -> dict[str, int]:
        """Shared orchestration for both HTTP-fetched and push-provided payloads."""
        adapter_type = self.get_adapter_type()
        
        logger.info(f"[{adapter_type}] Starting import from '{source_name}'")
        
        total_start = perf_counter()
        extract_start = perf_counter()
        fetched_payload = await fetch_callable()
        extract_elapsed_ms = (perf_counter() - extract_start) * 1000

        dispatcher = RealtimeProcessingDispatcherService(
            self.config, self._entity_enrichment_service, self._identifier_mapping_service,
            self._caching_service, self._matching_service,
        )

        transform_runtime_ms = fetched_payload.get("_transform_runtime_ms")
        transform_start = perf_counter()
        record_type, records = dispatcher.normalize_fetched_payload(fetched_payload)
        transform_elapsed_ms = float(transform_runtime_ms) if transform_runtime_ms is not None else (perf_counter() - transform_start) * 1000
        
        logger.info(f"[{adapter_type}] Fetched {len(records)} records from source (record_type={record_type})")

        load_start = perf_counter()
        try:
            return await dispatcher.sync_records(record_type, records, repository=repository, realtime_repository=realtime_repository, gtfs_repository=gtfs_repository, source_id=source_id, source_name=source_name)
        finally:
            load_elapsed_ms = (perf_counter() - load_start) * 1000
            total_elapsed_ms = (perf_counter() - total_start) * 1000
            logger.info("[%s] datasource run completed for '%s' (record_type=%s, total=%.2fms, extract=%.2fms, transform=%.2fms, load=%.2fms)", adapter_type, source_name, record_type, total_elapsed_ms, extract_elapsed_ms, transform_elapsed_ms, load_elapsed_ms)
