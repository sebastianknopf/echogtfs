"""
SIRI-Lite adapter for importing service alerts.

SIRI (Service Interface for Real Time Information) Lite is a simplified
profile of the SIRI standard for public transport real-time information.
"""

from typing import Any

from echogtfs.services.adapters.base import BaseAdapter


class SiriLiteAdapter(BaseAdapter):
    """
    Adapter for SIRI-Lite formatted service alert feeds.
    
    Configuration requirements:
        - endpoint: URL to the SIRI-Lite feed
        - token: Authentication token for the API
    """
    
    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "Endpoint URL",
            "required": True,
            "placeholder": "https://api.example.com/siri-lite",
            "help_text": "URL zum SIRI-Lite Feed",
        },
        {
            "name": "token",
            "type": "password",
            "label": "API Token",
            "required": True,
            "placeholder": "Bearer-Token oder API-Key",
            "help_text": "Authentifizierungs-Token für die API",
        },
    ]
    
    def _validate_config(self) -> None:
        """
        Validate SIRI-Lite configuration.
        
        Raises:
            ValueError: If required fields are missing
        """
        if "endpoint" not in self.config:
            raise ValueError("SiriLite adapter requires 'endpoint' in config")
        
        if "token" not in self.config:
            raise ValueError("SiriLite adapter requires 'token' in config")
        
        if not isinstance(self.config["endpoint"], str):
            raise ValueError("'endpoint' must be a string")
        
        if not isinstance(self.config["token"], str):
            raise ValueError("'token' must be a string")
    
    async def fetch_alerts(self) -> list[dict[str, Any]]:
        """
        Fetch service alerts from SIRI-Lite endpoint.
        
        Returns:
            List of ServiceAlert dictionaries ready for database insertion
        """
        # TODO: Implement SIRI-Lite feed parsing
        # 1. Fetch data from self.config["endpoint"] with self.config["token"]
        # 2. Parse SIRI-Lite XML/JSON format
        # 3. Transform to ServiceAlert structure
        # 4. Return list of alert dictionaries
        
        # MOCK implementation for testing
        from datetime import datetime, timedelta, UTC
        
        # Get source name from config for deterministic ID generation
        source_name = self.config.get("_source_name", "sirilite")
        
        now = datetime.now(UTC)
        start = int(now.timestamp())
        end = int((now + timedelta(hours=24)).timestamp())
        
        # Use deterministic ID instead of uuid.uuid4()
        # This ensures the same alert gets the same ID on every import
        alert_id = self._make_unique_id("siri-test-alert-1", source_name)
        
        return [
            {
                "id": alert_id,
                "cause": "MAINTENANCE",
                "effect": "DETOUR",
                "severity_level": "WARNING",
                "is_active": True,
                "translations": [
                    {
                        "language": "de-DE",
                        "header_text": "SIRI-Lite Test-Meldung",
                        "description_text": "Dies ist eine automatisch importierte Test-Meldung vom SIRI-Lite Adapter.",
                        "url": None,
                    },
                ],
                "active_periods": [
                    {
                        "start_time": start,
                        "end_time": end,
                    },
                ],
                "informed_entities": [
                    {
                        "route_id": "TEST_ROUTE_1",
                        "agency_id": None,
                        "route_type": None,
                        "stop_id": None,
                        "trip_id": None,
                        "direction_id": None,
                    },
                ],
            },
        ]
