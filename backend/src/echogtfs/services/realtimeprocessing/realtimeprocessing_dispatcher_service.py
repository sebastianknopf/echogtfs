from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from typing import Any

from echogtfs.services.caching.intf_caching_service import CachingServiceInterface
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.enrichment.intf_entity_enrichment import EntityEnrichmentInterface
from echogtfs.services.mapping.intf_identifier_mapping import IdentifierMappingInterface
from echogtfs.services.matching.intf_matching_service import MatchingServiceInterface
from echogtfs.services.matching.matching_service import MatchingService

logger = logging.getLogger("uvicorn")

from .service_alert_processing_service import ServiceAlertProcessingService
from .trip_update_processing_service import TripUpdateProcessingService
from .vehicle_position_processing_service import VehiclePositionProcessingService


class RealtimeProcessingDispatcherService:
    """Dispatch normalized realtime records to the entity-specific processor."""

    def __init__(self, config: dict[str, Any], entity_enrichment_service: EntityEnrichmentInterface, identifier_mapping_service: IdentifierMappingInterface, caching_service: CachingServiceInterface, matching_service: MatchingServiceInterface | None = None):
        kwargs = {
            "config": config,
            "entity_enrichment_service": entity_enrichment_service,
            "identifier_mapping_service": identifier_mapping_service,
            "caching_service": caching_service,
            "matching_service": matching_service,
        }

        self._processors = {
            "service_alerts": ServiceAlertProcessingService(**kwargs),
            "trip_updates": TripUpdateProcessingService(**kwargs),
            "vehicle_positions": VehiclePositionProcessingService(**kwargs),
        }

    @staticmethod
    def normalize_fetched_payload(fetched_payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        if not isinstance(fetched_payload, dict):
            raise ValueError("Fetched payload must be a dict with 'record_type' and 'records'")
        
        record_type = fetched_payload.get("record_type")
        records = fetched_payload.get("records")
        
        if not isinstance(record_type, str):
            raise ValueError("Fetched payload is missing string field 'record_type'")
        
        if not isinstance(records, list):
            raise ValueError("Fetched payload is missing list field 'records'")
        
        return record_type, records

    @staticmethod
    @asynccontextmanager
    async def _realtime_sync_transaction(realtime_repository: RealtimeRepositoryInterface):
        transaction = getattr(realtime_repository, "transaction", None)
        if transaction is None:
            yield
            return
        
        async with transaction():
            yield

    async def sync_records(self, record_type: str, records: list[dict[str, Any]], *, repository: SystemRepositoryInterface, realtime_repository: RealtimeRepositoryInterface, gtfs_repository: GtfsRepositoryInterface, source_id: int, source_name: str) -> dict[str, int]:
        processor = self._processors.get(record_type)
        if processor is None:
            raise NotImplementedError(f"Record type '{record_type}' is not supported by sync_records yet")
        
        async with self._realtime_sync_transaction(realtime_repository):
            return await processor.sync_records(repository=repository, realtime_repository=realtime_repository, gtfs_repository=gtfs_repository, source_id=source_id, source_name=source_name, records=records)
