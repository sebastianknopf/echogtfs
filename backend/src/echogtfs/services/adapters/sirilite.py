"""
SIRI-Lite adapter for importing service alerts.

SIRI (Service Interface for Real Time Information) Lite is a simplified
profile of the SIRI standard for public transport real-time information.

The adapter supports multiple regional dialect variants to handle different
implementations of the SIRI-Lite standard.
"""

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

import httpx

from echogtfs.models import SiriLiteDialect
from echogtfs.services.adapters.base import BaseAdapter

logger = logging.getLogger("uvicorn")


class SiriLiteAdapter(BaseAdapter):
    """
    Adapter for SIRI-Lite formatted service alert feeds.
    
    Supports multiple dialects for different regional implementations.
    
    Configuration requirements:
        - endpoint: URL to the SIRI-Lite feed
        - token: Authentication token for the API
        - dialect: Regional variant (swiss, nordic, france)
        - filter: Optional filter expression for data source
    """
    
    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "adapter.sirilite.endpoint.label",
            "required": True,
            "placeholder": "adapter.sirilite.endpoint.placeholder",
            "help_text": "adapter.sirilite.endpoint.help_text",
        },
        {
            "name": "token",
            "type": "password",
            "label": "adapter.sirilite.token.label",
            "required": True,
            "placeholder": "adapter.sirilite.token.placeholder",
            "help_text": "adapter.sirilite.token.help_text",
        },
        {
            "name": "dialect",
            "type": "enum",
            "label": "adapter.sirilite.dialect.label",
            "required": True,
            "options": ["swiss", "nordic", "france"],
            "help_text": "adapter.sirilite.dialect.help_text",
        },
        {
            "name": "filter",
            "type": "text",
            "label": "adapter.sirilite.filter.label",
            "required": False,
            "placeholder": "adapter.sirilite.filter.placeholder",
            "help_text": "adapter.sirilite.filter.help_text",
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
        
        if "dialect" not in self.config:
            raise ValueError("SiriLite adapter requires 'dialect' in config")
        
        if not isinstance(self.config["endpoint"], str):
            raise ValueError("'endpoint' must be a string")
        
        if not isinstance(self.config["token"], str):
            raise ValueError("'token' must be a string")
        
        # Validate dialect is a valid enum value
        try:
            SiriLiteDialect(self.config["dialect"])
        except ValueError:
            valid_dialects = [d.value for d in SiriLiteDialect]
            raise ValueError(
                f"'dialect' must be one of: {', '.join(valid_dialects)}"
            )
        
        # Filter is optional, but if provided, must be a string
        if "filter" in self.config and self.config["filter"]:
            if not isinstance(self.config["filter"], str):
                raise ValueError("'filter' must be a string")
    
    # SIRI XML namespace
    SIRI_NS = {'siri': 'http://www.siri.org.uk/siri'}
    
    async def fetch_alerts(self) -> list[dict[str, Any]]:
        """
        Fetch service alerts from SIRI-Lite endpoint.
        
        Dispatches to the appropriate dialect-specific implementation.
        
        Returns:
            List of ServiceAlert dictionaries ready for database insertion
        """
        dialect = SiriLiteDialect(self.config["dialect"])
        
        if dialect == SiriLiteDialect.SWISS:
            return await self._fetch_alerts_swiss()
        elif dialect == SiriLiteDialect.NORDIC:
            return await self._fetch_alerts_nordic()
        elif dialect == SiriLiteDialect.FRANCE:
            return await self._fetch_alerts_france()
        else:
            raise ValueError(f"Unknown dialect: {dialect}")
    
    async def _fetch_and_parse_xml(self) -> ET.Element:
        """
        Fetch and parse SIRI-Lite XML feed.
        
        This is a common method for all dialects.
        
        Returns:
            Parsed XML root element
            
        Raises:
            ValueError: If fetching or parsing fails
        """
        endpoint = self.config["endpoint"]
        token = self.config.get("token", "").strip()
        
        # Prepare headers
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        logger.info(f"[SiriLiteAdapter] Fetching SIRI-Lite feed from {endpoint}")
        
        # Fetch XML data
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(endpoint, headers=headers)
                response.raise_for_status()
                
                xml_content = response.text
                logger.info(f"[SiriLiteAdapter] Fetched {len(xml_content)} characters from feed")
        except httpx.HTTPError as e:
            logger.error(f"[SiriLiteAdapter] HTTP error fetching feed: {e}")
            raise ValueError(f"Failed to fetch SIRI-Lite feed: {e}")
        except Exception as e:
            logger.error(f"[SiriLiteAdapter] Unexpected error fetching feed: {e}")
            raise ValueError(f"Failed to fetch SIRI-Lite feed: {e}")
        
        # Parse XML
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error(f"[SiriLiteAdapter] Failed to parse XML: {e}")
            raise ValueError(f"Failed to parse SIRI-Lite XML: {e}")
        
        return root
    
    def _extract_situation_elements(
        self, 
        root: ET.Element
    ) -> tuple[list[ET.Element], str | None]:
        """
        Extract PtSituationElements from SIRI XML.
        
        This is a common method for all dialects.
        
        Args:
            root: Parsed XML root element
            
        Returns:
            Tuple of (list of PtSituationElements, producer_ref)
        """
        # Extract ProducerRef from ServiceDelivery
        producer_ref_elem = root.find('.//siri:ProducerRef', self.SIRI_NS)
        producer_ref = producer_ref_elem.text if producer_ref_elem is not None else None
        
        # Find all PtSituationElements
        situations = root.findall('.//siri:PtSituationElement', self.SIRI_NS)
        logger.info(f"[SiriLiteAdapter] Found {len(situations)} PtSituationElements")
        
        return situations, producer_ref
    
    def _is_in_publication_window(
        self, 
        situation: ET.Element, 
        current_timestamp: int
    ) -> bool:
        """
        Check if a situation is within its publication window.
        
        This is a common method for all dialects.
        Also filters out situations whose publication window starts more than 30 days in the future.
        
        Args:
            situation: PtSituationElement XML element
            current_timestamp: Current Unix timestamp
            
        Returns:
            True if situation is in publication window, False otherwise
        """
        publication_windows = situation.findall('siri:PublicationWindow', self.SIRI_NS)
        
        # If no publication windows, situation is valid
        if not publication_windows:
            return True
        
        # Maximum start time: 30 days in the future
        max_future_start = current_timestamp + (30 * 24 * 60 * 60)  # 30 days in seconds
        
        # Check if current time is within any publication window
        for pub_window in publication_windows:
            start_elem = pub_window.find('siri:StartTime', self.SIRI_NS)
            end_elem = pub_window.find('siri:EndTime', self.SIRI_NS)
            
            if start_elem is not None and end_elem is not None:
                try:
                    start_time = int(datetime.fromisoformat(
                        start_elem.text.replace('Z', '+00:00')
                    ).timestamp())
                    end_time = int(datetime.fromisoformat(
                        end_elem.text.replace('Z', '+00:00')
                    ).timestamp())
                    
                    # Skip if publication window starts more than 30 days in the future
                    if start_time > max_future_start:
                        continue
                    
                    # Check if current time is within this window
                    if start_time <= current_timestamp <= end_time:
                        return True
                    
                    # Check if window is in the future but within 30 days
                    if start_time > current_timestamp and start_time <= max_future_start:
                        return True
                except (ValueError, AttributeError) as e:
                    logger.warning(
                        f"[SiriLiteAdapter] Failed to parse PublicationWindow times: {e}"
                    )
        
        return False
    
    def _matches_participant_filter(self, situation: ET.Element) -> bool:
        """
        Check if a PtSituationElement matches the configured participant filter.
        
        Args:
            situation: PtSituationElement XML element
            
        Returns:
            True if situation matches filter or no filter is configured, False otherwise
        """
        # Get filter from config
        filter_str = self.config.get("filter", "").strip()
        
        # If no filter configured, accept all situations
        if not filter_str:
            return True
        
        # Parse filter: comma-separated participant refs, trimmed
        allowed_participants = {p.strip() for p in filter_str.split(",") if p.strip()}
        
        # Extract ParticipantRef from situation
        participant_ref_elem = situation.find('siri:ParticipantRef', self.SIRI_NS)
        participant_ref = participant_ref_elem.text.strip() if participant_ref_elem is not None and participant_ref_elem.text else None
        
        # Check if participant is in allowed list
        if participant_ref and participant_ref in allowed_participants:
            return True
        
        # Log filtered situations
        situation_number_elem = situation.find('siri:SituationNumber', self.SIRI_NS)
        situation_number = situation_number_elem.text if situation_number_elem is not None else "unknown"
        
        logger.debug(
            f"[SiriLiteAdapter] Filtering out situation {situation_number}: "
            f"ParticipantRef '{participant_ref}' not in allowed list: {', '.join(allowed_participants)}"
        )
        
        return False
    
    async def _fetch_alerts_swiss(self) -> list[dict[str, Any]]:
        """
        Fetch and parse alerts using Swiss dialect implementation.
        
        Returns:
            List of ServiceAlert dictionaries
            
        Raises:
            ValueError: If fetching or parsing fails
        """
        # Fetch and parse XML (common for all dialects)
        root = await self._fetch_and_parse_xml()
        
        # Extract situation elements (common for all dialects)
        situations, producer_ref = self._extract_situation_elements(root)
        
        if not situations:
            return []
        
        # Extract source name from config for ID generation
        source_name = self.config.get("_source_name", "sirilite")
        
        # Process each situation element with Swiss-specific logic
        alerts = []
        filtered_out_of_window = 0
        filtered_by_participant = 0
        current_timestamp = int(time.time())
        
        for situation in situations:
            try:
                # Check ParticipantRef filter (common logic)
                if not self._matches_participant_filter(situation):
                    filtered_by_participant += 1
                    continue
                
                # Check PublicationWindow(s) (common logic)
                if not self._is_in_publication_window(situation, current_timestamp):
                    filtered_out_of_window += 1
                    continue
                
                # Parse situation element with Swiss-specific logic
                alert = self._parse_situation_element_swiss(
                    situation, 
                    source_name, 
                    current_timestamp
                )
                
                if alert:
                    alerts.append(alert)
                
            except Exception as e:
                logger.error(
                    f"[SiriLiteAdapter:Swiss] Error processing situation: {e}", 
                    exc_info=True
                )
                # Continue with next situation instead of failing entirely
                continue
        
        logger.info(
            f"[SiriLiteAdapter:Swiss] Processed {len(alerts)} alerts "
            f"(filtered: {filtered_by_participant} by participant, "
            f"{filtered_out_of_window} out of publication window)"
        )
        
        return alerts
    
    def _parse_situation_element_swiss(
        self, 
        situation: ET.Element, 
        source_name: str,
        current_timestamp: int
    ) -> dict[str, Any] | None:
        """
        Parse a single PtSituationElement using Swiss dialect rules.
        
        Args:
            situation: PtSituationElement XML element
            source_name: Name of the data source (for ID generation)
            current_timestamp: Current Unix timestamp
            
        Returns:
            ServiceAlert dictionary or None if parsing fails
        """
        # Extract SituationNumber (use as alert ID)
        situation_number_elem = situation.find('siri:SituationNumber', self.SIRI_NS)
        if situation_number_elem is None:
            logger.warning("[SiriLiteAdapter:Swiss] Skipping situation without SituationNumber")
            return None
        situation_number = situation_number_elem.text
        
        # Generate unique ID
        alert_id = self._make_unique_id(situation_number, source_name)
        
        # Parse ValidityPeriod(s) to create active_periods
        active_periods = []
        validity_periods = situation.findall('siri:ValidityPeriod', self.SIRI_NS)
        for validity_period in validity_periods:
            start_elem = validity_period.find('siri:StartTime', self.SIRI_NS)
            end_elem = validity_period.find('siri:EndTime', self.SIRI_NS)
            
            start_time = None
            end_time = None
            
            if start_elem is not None:
                try:
                    start_time = int(datetime.fromisoformat(
                        start_elem.text.replace('Z', '+00:00')
                    ).timestamp())
                except (ValueError, AttributeError) as e:
                    logger.warning(
                        f"[SiriLiteAdapter:Swiss] Failed to parse ValidityPeriod StartTime: {e}"
                    )
            
            if end_elem is not None:
                try:
                    end_time = int(datetime.fromisoformat(
                        end_elem.text.replace('Z', '+00:00')
                    ).timestamp())
                except (ValueError, AttributeError) as e:
                    logger.warning(
                        f"[SiriLiteAdapter:Swiss] Failed to parse ValidityPeriod EndTime: {e}"
                    )
            
            active_periods.append({
                "start_time": start_time,
                "end_time": end_time,
            })
        
        # Parse translations from TextualContent
        # Look for TextualContentSize="L", or use first if not found
        translations_dict = {}  # {language: {header: ..., description_parts: [...], url: ...}}
        
        publishing_actions = situation.findall('.//siri:PublishingAction', self.SIRI_NS)
        
        # Collect all PassengerInformationActions
        passenger_infos = []
        for pub_action in publishing_actions:
            passenger_info = pub_action.find('siri:PassengerInformationAction', self.SIRI_NS)
            if passenger_info is not None:
                passenger_infos.append(passenger_info)
        
        # Select the appropriate PassengerInformationAction
        # Prefer first one with Perspective="general", otherwise use first available
        selected_passenger_info = None
        for passenger_info in passenger_infos:
            perspectives = passenger_info.findall('siri:Perspective', self.SIRI_NS)
            for perspective in perspectives:
                if perspective.text == 'general':
                    selected_passenger_info = passenger_info
                    break  # Found first with "general", use it
            if selected_passenger_info is not None:
                break  # Exit outer loop once we found one
        
        # If no "general" perspective found, use first PassengerInformationAction
        if selected_passenger_info is None and passenger_infos:
            selected_passenger_info = passenger_infos[0]
        
        # Collect TextualContent from selected PassengerInformationAction
        textual_contents = []
        if selected_passenger_info is not None:
            textual_contents = selected_passenger_info.findall('siri:TextualContent', self.SIRI_NS)
        
        # Find TextualContent with size L, or use first
        selected_textual_content = None
        for tc in textual_contents:
            size_elem = tc.find('siri:TextualContentSize', self.SIRI_NS)
            if size_elem is not None and size_elem.text == 'L':
                selected_textual_content = tc
                break
        
        # If no L size found, use first textual content
        if selected_textual_content is None and textual_contents:
            selected_textual_content = textual_contents[0]
        
        # Extract all text elements from selected TextualContent
        if selected_textual_content is not None:
            # Extract SummaryText elements for header_text
            summary_content = selected_textual_content.find('siri:SummaryContent', self.SIRI_NS)
            if summary_content is not None:
                summary_texts = summary_content.findall('siri:SummaryText', self.SIRI_NS)
                for summary_text in summary_texts:
                    lang = summary_text.get('{http://www.w3.org/XML/1998/namespace}lang', 'de')
                    lang = lang.lower()
                    header = summary_text.text or ""
                    
                    if lang not in translations_dict:
                        translations_dict[lang] = {'description_parts': []}
                    translations_dict[lang]['header_text'] = header
            
            # Build description_text from multiple content sections in specified order:
            # 1. ReasonText, 2. DescriptionText, 3. ConsequenceText, 
            # 4. RecommendationText, 5. DurationText, 6. Remark
            content_sections = [
                ('siri:ReasonContent', 'siri:ReasonText'),
                ('siri:DescriptionContent', 'siri:DescriptionText'),
                ('siri:ConsequenceContent', 'siri:ConsequenceText'),
                ('siri:RecommendationContent', 'siri:RecommendationText'),
                ('siri:DurationContent', 'siri:DurationText'),
                ('siri:RemarkContent', 'siri:Remark'),  # Note: 'Remark', not 'RemarkText'
            ]
            
            for content_element_name, text_element_name in content_sections:
                content = selected_textual_content.find(content_element_name, self.SIRI_NS)
                if content is not None:
                    text_elements = content.findall(text_element_name, self.SIRI_NS)
                    for text_elem in text_elements:
                        lang = text_elem.get('{http://www.w3.org/XML/1998/namespace}lang', 'de')
                        lang = lang.lower()
                        text = text_elem.text or ""
                        
                        if text.strip():  # Only add non-empty text
                            if lang not in translations_dict:
                                translations_dict[lang] = {'description_parts': []}
                            translations_dict[lang]['description_parts'].append(text)
            
            # Extract URL from InfoLink
            info_link = selected_textual_content.find('siri:InfoLink', self.SIRI_NS)
            if info_link is not None:
                uri_elem = info_link.find('siri:Uri', self.SIRI_NS)
                if uri_elem is not None and uri_elem.text:
                    url = uri_elem.text
                    # Set URL for all languages
                    for lang in translations_dict:
                        translations_dict[lang]['url'] = url
        
        # Convert translations_dict to list format, joining description parts
        translations = []
        for lang, data in translations_dict.items():
            # Join all description parts with double newline
            description_parts = data.get('description_parts', [])
            description_text = '\n\n'.join(description_parts) if description_parts else None
            
            translations.append({
                "language": lang,
                "header_text": data.get('header_text'),
                "description_text": description_text,
                "url": data.get('url'),
            })
        
        # Filter out situations without meaningful text information
        if not translations:
            logger.warning(
                f"[SiriLiteAdapter:Swiss] Skipping situation {situation_number}: "
                f"No translations found (no TextualContent available)"
            )
            return None
        
        # Check if at least one translation has header_text or description_text
        has_meaningful_text = any(
            t.get('header_text') or t.get('description_text')
            for t in translations
        )
        
        if not has_meaningful_text:
            logger.warning(
                f"[SiriLiteAdapter:Swiss] Skipping situation {situation_number}: "
                f"No meaningful text content (header_text and description_text are empty)"
            )
            return None
        
        # Parse InformedEntities from PublishingActions
        informed_entities = []
        
        for pub_action in publishing_actions:
            # Check both PublishAtScope and Consequences for Affects
            affects_elements = []
            
            publish_at_scope = pub_action.find('siri:PublishAtScope', self.SIRI_NS)
            if publish_at_scope is not None:
                affects_elem = publish_at_scope.find('siri:Affects', self.SIRI_NS)
                if affects_elem is not None:
                    affects_elements.append(affects_elem)
            
            # Also check Consequences (from situation level)
            consequences = situation.findall('.//siri:Consequence', self.SIRI_NS)
            for consequence in consequences:
                affects_elem = consequence.find('siri:Affects', self.SIRI_NS)
                if affects_elem is not None:
                    affects_elements.append(affects_elem)
            
            for affects in affects_elements:
                # Extract Networks (contains routes/lines and operators)
                networks = affects.findall('.//siri:AffectedNetwork', self.SIRI_NS)
                for network in networks:
                    affected_lines = network.findall('.//siri:AffectedLine', self.SIRI_NS)
                    for affected_line in affected_lines:
                        entity = {
                            "agency_id": None,
                            "route_id": None,
                            "route_type": None,
                            "stop_id": None,
                            "trip_id": None,
                            "direction_id": None,
                        }
                        
                        # Extract OperatorRef (agency_id)
                        operator_ref = affected_line.find('.//siri:OperatorRef', self.SIRI_NS)
                        if operator_ref is not None:
                            entity["agency_id"] = operator_ref.text
                        
                        # Extract LineRef (route_id)
                        line_ref = affected_line.find('siri:LineRef', self.SIRI_NS)
                        if line_ref is not None:
                            entity["route_id"] = line_ref.text
                        
                        informed_entities.append(entity)
                
                # Extract StopPlaces
                stop_places = affects.findall('.//siri:AffectedStopPlace', self.SIRI_NS)
                for stop_place in stop_places:
                    stop_place_ref = stop_place.find('siri:StopPlaceRef', self.SIRI_NS)
                    if stop_place_ref is not None:
                        informed_entities.append({
                            "agency_id": None,
                            "route_id": None,
                            "route_type": None,
                            "stop_id": stop_place_ref.text,
                            "trip_id": None,
                            "direction_id": None,
                        })
        
        # Map Severity
        severity_elem = situation.find('siri:Severity', self.SIRI_NS)
        severity = self._map_severity_swiss(
            severity_elem.text if severity_elem is not None else None
        )
        
        # Map AlertCause
        alert_cause_elem = situation.find('siri:AlertCause', self.SIRI_NS)
        cause = self._map_cause_swiss(
            alert_cause_elem.text if alert_cause_elem is not None else None
        )
        
        # Effect is not directly in Swiss SIRI, default to UNKNOWN_EFFECT
        effect = "UNKNOWN_EFFECT"
        
        return {
            "id": alert_id,
            "cause": cause,
            "effect": effect,
            "severity_level": severity,
            "is_active": True,
            "translations": translations,
            "active_periods": active_periods,
            "informed_entities": informed_entities,
        }
    
    def _map_severity_swiss(self, siri_severity: str | None) -> str:
        """
        Map SIRI-Lite Swiss severity to GTFS-RT AlertSeverityLevel.
        
        Args:
            siri_severity: SIRI severity value (e.g., "normal", "severe", "slight")
            
        Returns:
            AlertSeverityLevel string value
        """
        if not siri_severity:
            return "UNKNOWN_SEVERITY"
        
        severity_lower = siri_severity.lower()
        severity_mapping = {
            "slight": "INFO",
            "normal": "WARNING",
            "severe": "SEVERE",
            "verySevere": "SEVERE",
            "noimpact": "INFO",
        }
        
        return severity_mapping.get(severity_lower, "UNKNOWN_SEVERITY")
    
    def _map_cause_swiss(self, siri_cause: str | None) -> str:
        """
        Map SIRI-Lite Swiss AlertCause to GTFS-RT Cause.
        
        Args:
            siri_cause: SIRI AlertCause value
            
        Returns:
            AlertCause string value
        """
        if not siri_cause:
            return "UNKNOWN_CAUSE"
        
        cause_lower = siri_cause.lower()
        cause_mapping = {
            "undefinedalertcause": "UNKNOWN_CAUSE",
            "accident": "ACCIDENT",
            "strike": "STRIKE",
            "demonstration": "DEMONSTRATION",
            "technicalproblems": "TECHNICAL_PROBLEM",
            "roadworks": "CONSTRUCTION",
            "maintenance": "MAINTENANCE",
            "weather": "WEATHER",
            "staffsickness": "OTHER_CAUSE",
            "equipmentfailure": "TECHNICAL_PROBLEM",
        }
        
        return cause_mapping.get(cause_lower, "UNKNOWN_CAUSE")
    
    async def _fetch_alerts_nordic(self) -> list[dict[str, Any]]:
        """
        Fetch and parse alerts using Nordic dialect implementation.
        
        Returns:
            List of ServiceAlert dictionaries
            
        Raises:
            NotImplementedError: Implementation pending
        """
        raise NotImplementedError(
            "Nordic dialect implementation for SIRI-Lite is not yet available. "
            "This will be implemented to handle Nordic-specific data formats."
        )
    
    async def _fetch_alerts_france(self) -> list[dict[str, Any]]:
        """
        Fetch and parse alerts using France dialect implementation.
        
        Returns:
            List of ServiceAlert dictionaries
            
        Raises:
            NotImplementedError: Implementation pending
        """
        raise NotImplementedError(
            "France dialect implementation for SIRI-Lite is not yet available. "
            "This will be implemented to handle France-specific data formats."
        )
