"""
GTFS-Realtime adapter for importing service alerts.

GTFS-Realtime is a feed specification for public transportation schedules
and real-time updates including service alerts.
"""

import logging
import time
import uuid
from typing import Any

import httpx
from google.transit import gtfs_realtime_pb2

from echogtfs.services.adapters.base import BaseAdapter

logger = logging.getLogger("uvicorn")


class GtfsRtAdapter(BaseAdapter):
    """
    Adapter for GTFS-Realtime service alert feeds.
    
    Configuration requirements:
        - endpoint: URL to the GTFS-RT protobuf feed
        - token: Authentication token for the API (optional)
    """
    
    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "adapter.gtfsrt.endpoint.label",
            "required": True,
            "placeholder": "adapter.gtfsrt.endpoint.placeholder",
            "help_text": "adapter.gtfsrt.endpoint.help_text",
        },
        {
            "name": "token",
            "type": "password",
            "label": "adapter.gtfsrt.token.label",
            "required": False,
            "placeholder": "adapter.gtfsrt.token.placeholder",
            "help_text": "adapter.gtfsrt.token.help_text",
        },
    ]
    
    def _validate_config(self) -> None:
        """
        Validate GTFS-RT configuration.
        
        Raises:
            ValueError: If required fields are missing
        """
        if "endpoint" not in self.config:
            raise ValueError("GtfsRt adapter requires 'endpoint' in config")
        
        if not isinstance(self.config["endpoint"], str):
            raise ValueError("'endpoint' must be a string")
        
        # Token is optional, but if provided, must be a string
        if "token" in self.config and self.config["token"] is not None:
            if not isinstance(self.config["token"], str):
                raise ValueError("'token' must be a string")
    
    def _map_cause(self, gtfs_cause: int) -> str:
        """
        Map GTFS-RT Cause enum to our AlertCause string.
        
        Args:
            gtfs_cause: GTFS-RT Cause enum value
            
        Returns:
            AlertCause string value
        """
        cause_mapping = {
            1: "UNKNOWN_CAUSE",
            2: "OTHER_CAUSE",
            3: "TECHNICAL_PROBLEM",
            4: "STRIKE",
            5: "DEMONSTRATION",
            6: "ACCIDENT",
            7: "HOLIDAY",
            8: "WEATHER",
            9: "MAINTENANCE",
            10: "CONSTRUCTION",
            11: "POLICE_ACTIVITY",
            12: "MEDICAL_EMERGENCY",
        }
        return cause_mapping.get(gtfs_cause, "UNKNOWN_CAUSE")
    
    def _map_effect(self, gtfs_effect: int) -> str:
        """
        Map GTFS-RT Effect enum to our AlertEffect string.
        
        Args:
            gtfs_effect: GTFS-RT Effect enum value
            
        Returns:
            AlertEffect string value
        """
        effect_mapping = {
            1: "NO_SERVICE",
            2: "REDUCED_SERVICE",
            3: "SIGNIFICANT_DELAYS",
            4: "DETOUR",
            5: "ADDITIONAL_SERVICE",
            6: "MODIFIED_SERVICE",
            7: "OTHER_EFFECT",
            8: "UNKNOWN_EFFECT",
            9: "STOP_MOVED",
            10: "NO_EFFECT",
            11: "ACCESSIBILITY_ISSUE",
        }
        return effect_mapping.get(gtfs_effect, "UNKNOWN_EFFECT")
    
    def _map_severity(self, gtfs_severity: int) -> str:
        """
        Map GTFS-RT SeverityLevel enum to our AlertSeverityLevel string.
        
        Args:
            gtfs_severity: GTFS-RT SeverityLevel enum value
            
        Returns:
            AlertSeverityLevel string value
        """
        severity_mapping = {
            1: "UNKNOWN_SEVERITY",
            2: "INFO",
            3: "WARNING",
            4: "SEVERE",
        }
        return severity_mapping.get(gtfs_severity, "UNKNOWN_SEVERITY")
    
    async def fetch_alerts(self) -> list[dict[str, Any]]:
        """
        Fetch service alerts from GTFS-RT endpoint.
        
        Returns:
            List of ServiceAlert dictionaries ready for database insertion
        """
        endpoint = self.config["endpoint"]
        token = self.config.get("token", "").strip()
        
        # Prepare headers
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        logger.info(f"[GtfsRtAdapter] Fetching GTFS-RT feed from {endpoint}")
        
        # Fetch protobuf data
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(endpoint, headers=headers)
                response.raise_for_status()
                
                # Log final URL after redirects
                final_url = str(response.url)
                if final_url != endpoint:
                    logger.info(f"[GtfsRtAdapter] Redirected to: {final_url}")
                
                protobuf_data = response.content
                logger.info(f"[GtfsRtAdapter] Fetched {len(protobuf_data)} bytes from feed")
        except httpx.HTTPError as e:
            logger.error(f"[GtfsRtAdapter] HTTP error fetching feed: {e}")
            raise ValueError(f"Failed to fetch GTFS-RT feed: {e}")
        except Exception as e:
            logger.error(f"[GtfsRtAdapter] Unexpected error fetching feed: {e}")
            raise ValueError(f"Failed to fetch GTFS-RT feed: {e}")
        
        # Parse protobuf
        feed = gtfs_realtime_pb2.FeedMessage()
        try:
            feed.ParseFromString(protobuf_data)
        except Exception as e:
            logger.error(f"[GtfsRtAdapter] Failed to parse protobuf: {e}")
            raise ValueError(f"Failed to parse GTFS-RT protobuf: {e}")
        
        logger.info(f"[GtfsRtAdapter] Parsed {len(feed.entity)} entities from feed")
        
        # Extract source name from config (used for ID generation)
        # Note: The actual source name will be set by alert_import.py
        source_name = self.config.get("_source_name", "gtfsrt")
        
        alerts = []
        filtered_not_yet_valid = 0
        filtered_expired = 0
        
        for entity in feed.entity:
            if not entity.HasField("alert"):
                continue
            
            alert = entity.alert
            
            # Generate unique ID
            alert_id = self._make_unique_id(entity.id, source_name)
            
            # Parse cause, effect, severity
            cause = self._map_cause(alert.cause) if alert.HasField("cause") else "UNKNOWN_CAUSE"
            effect = self._map_effect(alert.effect) if alert.HasField("effect") else "UNKNOWN_EFFECT"
            severity = self._map_severity(alert.severity_level) if alert.HasField("severity_level") else "UNKNOWN_SEVERITY"
            
            # Parse translations
            translations = []
            if alert.HasField("header_text"):
                for translation in alert.header_text.translation:
                    language = translation.language if translation.HasField("language") else "de-DE"
                    header = translation.text if translation.HasField("text") else None
                    
                    # Get corresponding description
                    description = None
                    if alert.HasField("description_text"):
                        for desc_trans in alert.description_text.translation:
                            if (desc_trans.HasField("language") and desc_trans.language == language) or \
                               (not desc_trans.HasField("language") and language == "de-DE"):
                                description = desc_trans.text if desc_trans.HasField("text") else None
                                break
                    
                    # Get corresponding URL
                    url = None
                    if alert.HasField("url"):
                        for url_trans in alert.url.translation:
                            if (url_trans.HasField("language") and url_trans.language == language) or \
                               (not url_trans.HasField("language") and language == "de-DE"):
                                url = url_trans.text if url_trans.HasField("text") else None
                                break
                    
                    translations.append({
                        "language": language,
                        "header_text": header,
                        "description_text": description,
                        "url": url,
                    })
            
            # If no translations found, create a default one
            if not translations:
                translations.append({
                    "language": "de-DE",
                    "header_text": "Service Alert",
                    "description_text": None,
                    "url": None,
                })
            
            # Parse active periods
            active_periods = []
            for period in alert.active_period:
                start_time = period.start if period.HasField("start") else None
                end_time = period.end if period.HasField("end") else None
                active_periods.append({
                    "start_time": start_time,
                    "end_time": end_time,
                })
            
            # Filter alerts based on validity period
            if active_periods:
                current_timestamp = int(time.time())
                
                # Check if alert starts more than 1 month (30 days) in the future
                earliest_start = min(
                    (p["start_time"] for p in active_periods if p["start_time"] is not None),
                    default=None
                )
                one_month_in_seconds = 30 * 24 * 60 * 60  # 2592000 seconds
                if earliest_start is not None and earliest_start > (current_timestamp + one_month_in_seconds):
                    logger.debug(
                        f"[GtfsRtAdapter] Skipping alert {entity.id}: starts more than 1 month in the future "
                        f"(starts at {earliest_start}, now is {current_timestamp})"
                    )
                    filtered_not_yet_valid += 1
                    continue
                
                # Check if alert has expired (latest end_time is in the past)
                latest_end = max(
                    (p["end_time"] for p in active_periods if p["end_time"] is not None),
                    default=None
                )
                if latest_end is not None and latest_end < current_timestamp:
                    logger.debug(
                        f"[GtfsRtAdapter] Skipping alert {entity.id}: expired "
                        f"(ended at {latest_end}, now is {current_timestamp})"
                    )
                    filtered_expired += 1
                    continue
            
            # Parse informed entities
            informed_entities = []
            for entity_selector in alert.informed_entity:
                informed_entities.append({
                    "agency_id": entity_selector.agency_id if entity_selector.HasField("agency_id") else None,
                    "route_id": entity_selector.route_id if entity_selector.HasField("route_id") else None,
                    "route_type": entity_selector.route_type if entity_selector.HasField("route_type") else None,
                    "stop_id": entity_selector.stop_id if entity_selector.HasField("stop_id") else None,
                    "trip_id": entity_selector.trip.trip_id if entity_selector.HasField("trip") and entity_selector.trip.HasField("trip_id") else None,
                    "direction_id": entity_selector.trip.direction_id if entity_selector.HasField("trip") and entity_selector.trip.HasField("direction_id") else None,
                })
            
            alerts.append({
                "id": alert_id,
                "cause": cause,
                "effect": effect,
                "severity_level": severity,
                "is_active": True,
                "translations": translations,
                "active_periods": active_periods,
                "informed_entities": informed_entities,
            })
        
        # Log filtering statistics
        total_filtered = filtered_not_yet_valid + filtered_expired
        if total_filtered > 0:
            logger.info(
                f"[GtfsRtAdapter] Filtered {total_filtered} alerts: "
                f"{filtered_not_yet_valid} not yet valid, {filtered_expired} expired"
            )
        
        logger.info(f"[GtfsRtAdapter] Transformed {len(alerts)} valid alerts")
        
        return alerts
