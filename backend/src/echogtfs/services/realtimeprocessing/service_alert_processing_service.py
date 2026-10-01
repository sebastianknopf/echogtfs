from __future__ import annotations

import logging
from typing import Any

from echogtfs.enum.system import InvalidReferencePolicy
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface

logger = logging.getLogger("uvicorn")

from .base import RealtimeProcessingServiceBase


class ServiceAlertProcessingService(RealtimeProcessingServiceBase):

    async def sync_records(
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

            _missing_effect = object()

            for alert_data in alert_dicts:
                is_closing_alert = bool(alert_data.get("is_closing_alert", False))
                original_effect = alert_data.get("effect", _missing_effect)
                self._entity_enrichment_service.apply_enrichment(
                    alert_data,
                    self.get_adapter_type(),
                )

                if is_closing_alert:
                    if original_effect is _missing_effect:
                        alert_data.pop("effect", None)
                    else:
                        alert_data["effect"] = original_effect
        
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
                mapped_entity_data = self._identifier_mapping_service.apply_mapping(
                    entity_data,
                )

                # For DISCARD_INVALID_ELEMENTS policy, validate and clean individual fields
                if policy == InvalidReferencePolicy.DISCARD_INVALID_ELEMENTS:
                    cleaned_entity, has_valid_ref = self._validate_and_clean_entity_elements(
                        mapped_entity_data,
                        gtfs_entities,
                    )

                    cleaned_entity_flags = self._merge_provided_entity_validation_flags(
                        cleaned_entity,
                        self._entity_validation_flags(
                            cleaned_entity,
                            gtfs_entities,
                        ),
                    )
                    cleaned_entity.update(cleaned_entity_flags)
                    is_valid_entity = bool(
                        has_valid_ref and self._is_entity_valid_flags(cleaned_entity_flags)
                    )

                    if not is_valid_entity:
                        has_invalid_entity = True
                        logger.debug(
                            f"[{self.get_adapter_type()}] Entity has no valid references in alert {alert_id}: "
                            f"{mapped_entity_data}"
                        )
                    
                    validated_entities.append((cleaned_entity, is_valid_entity))
                else:
                    # Standard validation for other policies
                    validation_flags = self._merge_provided_entity_validation_flags(
                        mapped_entity_data,
                        self._entity_validation_flags(
                            mapped_entity_data,
                            gtfs_entities,
                        ),
                    )
                    mapped_entity_data.update(validation_flags)
                    is_valid_entity = self._is_entity_valid_flags(validation_flags)
                    
                    if not is_valid_entity:
                        has_invalid_entity = True
                        logger.debug(
                            f"[{self.get_adapter_type()}] Invalid entity reference in alert {alert_id}: "
                            f"{mapped_entity_data}"
                        )
                    
                    validated_entities.append((mapped_entity_data, is_valid_entity))
            
            # Apply invalid reference policy
            should_skip_alert = False
            should_deactivate_alert = False
            entities_to_create = [entity for entity, _ in validated_entities]
            
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
                    entities_to_create = [entity for entity, is_valid_entity in validated_entities if is_valid_entity]
                    
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
                    entities_to_create = [entity for entity, is_valid_entity in validated_entities if is_valid_entity]
                    
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
                entities_to_create = self._deduplicate_entities(entities_to_create)
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
