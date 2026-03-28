"""
Base adapter for external data sources.

All data source adapters must inherit from BaseAdapter and implement
the required methods for fetching and transforming service alerts.
"""

from abc import ABC, abstractmethod
import logging
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("uvicorn")


class BaseAdapter(ABC):
    """
    Abstract base class for data source adapters.
    
    Each adapter handles fetching data from a specific external format
    and transforming it into the ServiceAlert database structure.
    """
    
    # Each adapter must define its configuration schema
    # List of dicts with keys: name, type, label, required, placeholder, help_text
    CONFIG_SCHEMA: list[dict[str, Any]] = []
    
    def __init__(self, config: dict[str, Any]):
        """
        Initialize the adapter with configuration.
        
        Args:
            config: Configuration dictionary containing at minimum:
                    - endpoint: URL endpoint for the data source
                    Additional fields depend on the specific adapter.
        """
        self.config = config
        self._validate_config()
    
    @abstractmethod
    def _validate_config(self) -> None:
        """
        Validate the adapter configuration.
        
        Raises:
            ValueError: If required configuration fields are missing or invalid
        """
        pass
    
    @abstractmethod
    async def fetch_alerts(self) -> list[dict[str, Any]]:
        """
        Fetch service alerts from the external data source.
        
        Returns:
            List of dictionaries representing ServiceAlert data ready for
            database insertion. Each dictionary should have the structure:
            {
                "cause": "MAINTENANCE",
                "effect": "DETOUR",
                "severity_level": "WARNING",
                "source": "adapter_name",
                "is_active": True,
                "translations": [
                    {
                        "language": "de-DE",
                        "header_text": "...",
                        "description_text": "...",
                        "url": "..."
                    }
                ],
                "active_periods": [
                    {
                        "start_time": 1234567890,
                        "end_time": 1234567999
                    }
                ],
                "informed_entities": [
                    {
                        "route_id": "123",
                        "stop_id": "456",
                        ...
                    }
                ]
            }
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
        Create a unique UUID for an alert based on its original ID and source.
        
        If the original ID is already a UUID, return it as-is.
        Otherwise, create a deterministic UUID using namespace UUID5.
        
        Args:
            original_id: Original alert ID from external feed
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
    
    def get_adapter_type(self) -> str:
        """
        Get the type identifier of this adapter.
        
        Returns:
            Adapter type string (e.g., "sirilite", "gtfsrt")
        """
        return self.__class__.__name__.replace("Adapter", "").lower()
    
    @classmethod
    def get_config_schema(cls) -> list[dict[str, Any]]:
        """
        Get the configuration schema for this adapter.
        
        Returns:
            List of configuration field definitions
        """
        return [dict(field) for field in cls.CONFIG_SCHEMA]
    
    async def _load_mappings(self, db: AsyncSession, source_id: int) -> dict[str, dict[str, str]]:
        """Load mappings for the specified data source.
        
        Returns a nested dictionary: {entity_type: {external_key: gtfs_value}}
        For example: {"agency": {"external_id_1": "gtfs_agency_1"}, "route": {"ext_route_1": "gtfs_route_1"}}
        
        Args:
            db: Database session
            source_id: ID of the data source to load mappings for
        """
        from echogtfs.models import DataSourceMapping
        
        # Load all mappings for this data source
        result = await db.execute(
            select(DataSourceMapping).where(DataSourceMapping.data_source_id == source_id)
        )
        mappings = result.scalars().all()
        
        # Structure mappings by entity type
        structured_mappings = {}
        for mapping in mappings:
            entity_type = mapping.entity_type
            if entity_type not in structured_mappings:
                structured_mappings[entity_type] = {}
            structured_mappings[entity_type][mapping.key] = mapping.value
        
        return structured_mappings
    
    def _apply_entity_mappings(self, entity_data: dict[str, Any], mappings: dict[str, dict[str, str]]) -> dict[str, Any]:
        """Apply mappings to informed entity data.
        
        Args:
            entity_data: Dictionary with entity fields (agency_id, route_id, stop_id, etc.)
            mappings: Loaded mappings from _load_mappings()
        
        Returns:
            Updated entity data with mapped values (if mappings exist)
        """
        # Create a copy to avoid modifying the original
        mapped_entity = entity_data.copy()
        
        # Apply mappings for each supported entity type
        if "agency_id" in mapped_entity and mapped_entity["agency_id"]:
            original_value = mapped_entity["agency_id"]
            mapped_entity["agency_id"] = mappings.get("agency", {}).get(original_value, original_value)
        
        if "route_id" in mapped_entity and mapped_entity["route_id"]:
            original_value = mapped_entity["route_id"]
            mapped_entity["route_id"] = mappings.get("route", {}).get(original_value, original_value)
        
        if "stop_id" in mapped_entity and mapped_entity["stop_id"]:
            original_value = mapped_entity["stop_id"]
            mapped_entity["stop_id"] = mappings.get("stop", {}).get(original_value, original_value)
        
        return mapped_entity
    
    async def sync_alerts(
        self, 
        db: AsyncSession, 
        source_id: int, 
        source_name: str
    ) -> dict[str, int]:
        """
        Synchronize alerts from the external data source to the database.
        
        This method orchestrates the complete sync process:
        1. Fetches alerts from the external source (via fetch_alerts)
        2. Compares with existing alerts in the database
        3. Updates existing alerts (preserving is_active flag)
        4. Inserts new alerts
        5. Deletes alerts that no longer exist in the source
        
        Args:
            db: Database session
            source_id: Database ID of the data source
            source_name: Name of the data source (for logging and deterministic IDs)
            
        Returns:
            Dictionary with keys 'added', 'updated', 'deleted' containing counts
        """
        # Import models here to avoid circular dependency
        from echogtfs.models import (
            ServiceAlert, 
            ServiceAlertTranslation, 
            ServiceAlertActivePeriod, 
            ServiceAlertInformedEntity
        )
        
        # Fetch alerts from external source
        logger.info(f"[{self.get_adapter_type()}] Fetching alerts from {source_name}")
        alert_dicts = await self.fetch_alerts()
        
        # Load mappings for this data source
        mappings = await self._load_mappings(db, source_id)
        
        # Get IDs of alerts from the feed
        incoming_alert_ids = {alert_data["id"] for alert_data in alert_dicts}
        
        # Get existing alerts from this data source
        result = await db.execute(
            select(ServiceAlert).where(ServiceAlert.data_source_id == source_id)
        )
        existing_alerts = {alert.id: alert for alert in result.scalars().all()}
        existing_alert_ids = set(existing_alerts.keys())
        
        # Also check if any incoming alerts exist in DB with different/null data_source_id
        # This handles migration scenarios and prevents duplicate key errors
        if incoming_alert_ids:
            result_by_id = await db.execute(
                select(ServiceAlert).where(ServiceAlert.id.in_(incoming_alert_ids))
            )
            alerts_by_id = {alert.id: alert for alert in result_by_id.scalars().all()}
            
            # Merge into existing_alerts - alerts with matching IDs should be updated
            for alert_id, alert in alerts_by_id.items():
                if alert_id not in existing_alerts:
                    existing_alerts[alert_id] = alert
                    existing_alert_ids.add(alert_id)
        
        # Determine which alerts to add, update, or delete
        alerts_to_add = incoming_alert_ids - existing_alert_ids
        alerts_to_update = incoming_alert_ids & existing_alert_ids
        # Only delete alerts that belong to this data source
        alerts_to_delete = {
            aid for aid, alert in existing_alerts.items() 
            if alert.data_source_id == source_id and aid not in incoming_alert_ids
        }
        
        logger.info(
            f"[{self.get_adapter_type()}] Changes for {source_name}: "
            f"{len(alerts_to_add)} new, {len(alerts_to_update)} updated, "
            f"{len(alerts_to_delete)} deleted"
        )
        
        # Delete alerts that are no longer in the feed
        if alerts_to_delete:
            await db.execute(
                delete(ServiceAlert).where(ServiceAlert.id.in_(alerts_to_delete))
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
            
            if alert_id in alerts_to_update:
                # UPDATE existing alert (preserve is_active field)
                existing_alert = existing_alerts[alert_id]
                
                # Update main alert fields (except is_active)
                existing_alert.cause = alert_data["cause"]
                existing_alert.effect = alert_data["effect"]
                existing_alert.severity_level = alert_data["severity_level"]
                existing_alert.source = alert_data["source"]
                existing_alert.data_source_id = source_id  # Ensure data_source_id is set
                # is_active is intentionally NOT updated to allow manual suppression
                
                # Delete and recreate child objects (translations, periods, entities)
                # This is simpler than trying to update each one individually
                await db.execute(
                    delete(ServiceAlertTranslation).where(
                        ServiceAlertTranslation.alert_id == alert_id
                    )
                )
                await db.execute(
                    delete(ServiceAlertActivePeriod).where(
                        ServiceAlertActivePeriod.alert_id == alert_id
                    )
                )
                await db.execute(
                    delete(ServiceAlertInformedEntity).where(
                        ServiceAlertInformedEntity.alert_id == alert_id
                    )
                )
                
                # Create new translations
                for trans_data in translations_data:
                    translation = ServiceAlertTranslation(
                        alert_id=alert_id,
                        **trans_data
                    )
                    db.add(translation)
                
                # Create new active periods
                for period_data in periods_data:
                    period = ServiceAlertActivePeriod(
                        alert_id=alert_id,
                        **period_data
                    )
                    db.add(period)
                
                # Create new informed entities
                for entity_data in entities_data:
                    # Apply mappings to entity data
                    mapped_entity_data = self._apply_entity_mappings(entity_data, mappings)
                    entity = ServiceAlertInformedEntity(
                        alert_id=alert_id,
                        **mapped_entity_data
                    )
                    db.add(entity)
            else:
                # INSERT new alert
                alert = ServiceAlert(**alert_data)
                db.add(alert)
                await db.flush()  # Ensure the alert is persisted before adding children
                
                # Create translations
                for trans_data in translations_data:
                    translation = ServiceAlertTranslation(
                        alert_id=alert.id,
                        **trans_data
                    )
                    db.add(translation)
                
                # Create active periods
                for period_data in periods_data:
                    period = ServiceAlertActivePeriod(
                        alert_id=alert.id,
                        **period_data
                    )
                    db.add(period)
                
                # Create informed entities
                for entity_data in entities_data:
                    # Apply mappings to entity data
                    mapped_entity_data = self._apply_entity_mappings(entity_data, mappings)
                    entity = ServiceAlertInformedEntity(
                        alert_id=alert.id,
                        **mapped_entity_data
                    )
                    db.add(entity)
        
        logger.info(
            f"[{self.get_adapter_type()}] Successfully synced {len(alert_dicts)} alerts "
            f"from {source_name}"
        )
        
        return {
            "added": len(alerts_to_add),
            "updated": len(alerts_to_update),
            "deleted": len(alerts_to_delete),
        }

