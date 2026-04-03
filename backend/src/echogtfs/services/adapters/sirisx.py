"""
SIRI-SX adapter for importing service alerts.

SIRI-SX (Service Interface for Real Time Information - Situation Exchange)
is a standard for exchanging information about incidents, disruptions and
other situations affecting public transport services.
"""

import logging
import re
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

from echogtfs.models import SiriSxDialect, SiriSxMethod
from echogtfs.services.adapters.base import BaseAdapter

logger = logging.getLogger("uvicorn")


class SiriSxAdapter(BaseAdapter):
    """
    Adapter for SIRI-SX formatted service alert feeds.
    
    Supports request/response method for querying SIRI-SX endpoints.
    
    Configuration requirements:
        - endpoint: URL to the SIRI-SX endpoint (supports placeholders)
        - participantref: Participant reference identifier
        - method: Request method (currently only "request/response")
        - dialect: Regional variant (currently only "sirisx")
        - filter: Optional filter expression for data source
    """
    
    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "Endpoint URL",
            "required": True,
            "placeholder": "https://api.example.com/siri-sx?RequestorRef={participantRef}",
            "help_text": "URL zum SIRI-SX Feed",
        },
        {
            "name": "participantref",
            "type": "text",
            "label": "Participant Reference",
            "required": True,
            "placeholder": "YOUR_PARTICIPANT_ID",
            "help_text": "Leitstellenkennung",
        },
        {
            "name": "method",
            "type": "enum",
            "label": "Methode",
            "required": True,
            "options": ["request/response", "publish/subscribe"],
            "help_text": "Anfrage-Methode (Request/Response oder Publish/Subscribe)",
        },
        {
            "name": "dialect",
            "type": "enum",
            "label": "Dialekt",
            "required": True,
            "options": ["sirisx"],
            "help_text": "Regionale Implementierungsvariante (SIRI-SX)",
        },
        {
            "name": "filter",
            "type": "text",
            "label": "Filter",
            "required": False,
            "placeholder": "Optionaler Filter-Ausdruck",
            "help_text": "Filter zur Einschränkung der Datenquelle",
        },
    ]
    
    def _validate_config(self) -> None:
        """
        Validate SIRI-SX configuration.
        
        Raises:
            ValueError: If required fields are missing or invalid
        """
        if "endpoint" not in self.config:
            raise ValueError("SiriSx adapter requires 'endpoint' in config")
        
        if "participantref" not in self.config:
            raise ValueError("SiriSx adapter requires 'participantref' in config")
        
        if "method" not in self.config:
            raise ValueError("SiriSx adapter requires 'method' in config")
        
        if "dialect" not in self.config:
            raise ValueError("SiriSx adapter requires 'dialect' in config")
        
        if not isinstance(self.config["endpoint"], str):
            raise ValueError("'endpoint' must be a string")
        
        if not isinstance(self.config["participantref"], str):
            raise ValueError("'participantref' must be a string")
        
        # Validate method is a valid enum value
        try:
            SiriSxMethod(self.config["method"])
        except ValueError:
            valid_methods = [m.value for m in SiriSxMethod]
            raise ValueError(
                f"Invalid method '{self.config['method']}'. "
                f"Valid options: {', '.join(valid_methods)}"
            )
        
        # Validate dialect is a valid enum value
        try:
            SiriSxDialect(self.config["dialect"])
        except ValueError:
            valid_dialects = [d.value for d in SiriSxDialect]
            raise ValueError(
                f"Invalid dialect '{self.config['dialect']}'. "
                f"Valid options: {', '.join(valid_dialects)}"
            )
    
    def _resolve_placeholders(self, url: str) -> str:
        """
        Replace placeholders in URL with actual values from config.
        
        Currently supported placeholders:
            - {participantRef}: Replaced with participantref from config
        
        Args:
            url: URL string potentially containing placeholders
            
        Returns:
            URL with placeholders replaced
        """
        # Replace {participantRef} with the actual value
        url = re.sub(
            r'\{participantRef\}',
            self.config.get('participantref', ''),
            url,
            flags=re.IGNORECASE
        )
        
        return url
    
    def _build_request_xml(self) -> str:
        """
        Build SIRI-SX ServiceRequest XML payload.
        
        Returns:
            XML string for the SIRI-SX request
        """
        # Get current timestamp in ISO8601 format
        timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        
        # Create root element with namespace
        siri = ET.Element(
            'Siri',
            attrib={
                'xmlns': 'http://www.siri.org.uk/siri',
                'version': '2.0'
            }
        )
        
        # ServiceRequest element
        service_request = ET.SubElement(siri, 'ServiceRequest')
        
        # RequestTimestamp
        request_timestamp = ET.SubElement(service_request, 'RequestTimestamp')
        request_timestamp.text = timestamp
        
        # RequestorRef
        requestor_ref = ET.SubElement(service_request, 'RequestorRef')
        requestor_ref.text = self.config.get('participantref', '')
        
        # SituationExchangeRequest
        situation_exchange = ET.SubElement(
            service_request,
            'SituationExchangeRequest',
            attrib={'version': '2.0'}
        )
        
        # RequestTimestamp within SituationExchangeRequest
        sx_timestamp = ET.SubElement(situation_exchange, 'RequestTimestamp')
        sx_timestamp.text = timestamp
        
        # Convert to string with XML declaration
        xml_string = ET.tostring(siri, encoding='unicode', method='xml')
        return f'<?xml version="1.0" encoding="UTF-8"?>{xml_string}'
    
    async def fetch_alerts(self) -> list[dict[str, Any]]:
        """
        Fetch service alerts from the SIRI-SX data source.
        
        Dispatches to the appropriate dialect-specific implementation.
        
        Returns:
            List of dictionaries representing ServiceAlert data ready for
            database insertion.
            
        Raises:
            NotImplementedError: If method is publish/subscribe
        """
        dialect = SiriSxDialect(self.config["dialect"])
        
        if dialect == SiriSxDialect.SIRISX:
            return await self._fetch_alerts_sirisx()
        else:
            raise ValueError(f"Unknown dialect: {dialect}")
    
    async def _fetch_alerts_sirisx(self) -> list[dict[str, Any]]:
        """
        Fetch and parse alerts using SIRI-SX dialect implementation.
        
        Returns:
            List of ServiceAlert dictionaries
            
        Raises:
            ValueError: If fetching or parsing fails
            NotImplementedError: If method is publish/subscribe
        """
        method = self.config.get('method')
        
        # Check if method is supported
        if method == SiriSxMethod.PUBLISH_SUBSCRIBE.value:
            raise NotImplementedError(
                "Method 'publish/subscribe' is not yet supported. "
                "Please use 'request/response' instead."
            )
        
        # Resolve placeholders in endpoint URL
        endpoint_url = self._resolve_placeholders(self.config['endpoint'])
        
        # Log method and URL
        logger.info(f"[SiriSxAdapter] Using method: {method}")
        logger.info(f"[SiriSxAdapter] Requesting URL: {endpoint_url}")
        
        # Build XML request payload
        xml_payload = self._build_request_xml()
        
        # Make POST request
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint_url,
                    content=xml_payload,
                    headers={
                        'Content-Type': 'application/xml; charset=utf-8',
                    },
                )
                response.raise_for_status()
                xml_content = response.text
                logger.info(f"[SiriSxAdapter] Fetched {len(xml_content)} characters from feed")
        except httpx.HTTPError as e:
            logger.error(f"[SiriSxAdapter] HTTP error fetching feed: {e}")
            raise ValueError(f"Failed to fetch SIRI-SX feed: {e}")
        except Exception as e:
            logger.error(f"[SiriSxAdapter] Unexpected error fetching feed: {e}")
            raise ValueError(f"Failed to fetch SIRI-SX feed: {e}")
        
        # Parse XML
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error(f"[SiriSxAdapter] Failed to parse XML: {e}")
            raise ValueError(f"Failed to parse SIRI-SX XML: {e}")
        
        # Define SIRI namespace
        SIRI_NS = {'siri': 'http://www.siri.org.uk/siri'}
        
        # Extract ProducerRef from ServiceDelivery
        producer_ref_elem = root.find('.//siri:ProducerRef', SIRI_NS)
        producer_ref = producer_ref_elem.text if producer_ref_elem is not None else None
        
        # Find all PtSituationElements
        situations = root.findall('.//siri:PtSituationElement', SIRI_NS)
        logger.info(f"[SiriSxAdapter] Found {len(situations)} PtSituationElements")
        
        if not situations:
            return []
        
        # Extract source name from config for ID generation
        source_name = self.config.get("_source_name", "sirisx")
        
        # Process each situation element
        alerts = []
        filtered_out_of_window = 0
        filtered_by_participant = 0
        current_timestamp = int(time.time())
        
        for situation in situations:
            try:
                # Check ParticipantRef filter
                if not self._matches_participant_filter(situation, SIRI_NS):
                    filtered_by_participant += 1
                    continue
                
                # Check PublicationWindow(s)
                if not self._is_in_publication_window(situation, current_timestamp, SIRI_NS):
                    filtered_out_of_window += 1
                    continue
                
                alert = self._parse_situation_element_sirisx(
                    situation,
                    source_name,
                    current_timestamp,
                    SIRI_NS
                )
                
                if alert:
                    alerts.append(alert)
            except Exception as e:
                situation_number_elem = situation.find('siri:SituationNumber', SIRI_NS)
                situation_number = situation_number_elem.text if situation_number_elem is not None else "unknown"
                logger.error(
                    f"[SiriSxAdapter] Error parsing situation {situation_number}: {e}"
                )
                continue
        
        # Log statistics
        logger.info(
            f"[SiriSxAdapter] Processed {len(alerts)} alerts "
            f"(filtered out: {filtered_by_participant} by participant, "
            f"{filtered_out_of_window} out of publication window)"
        )
        return alerts
    
    def _parse_situation_element_sirisx(
        self,
        situation: ET.Element,
        source_name: str,
        current_timestamp: int,
        SIRI_NS: dict[str, str]
    ) -> dict[str, Any] | None:
        """
        Parse a single PtSituationElement using SIRI-SX dialect rules.
        
        Args:
            situation: PtSituationElement XML element
            source_name: Name of the data source (for ID generation)
            current_timestamp: Current Unix timestamp
            SIRI_NS: SIRI namespace dictionary
            
        Returns:
            ServiceAlert dictionary or None if parsing fails
        """
        # Extract SituationNumber (use as alert ID)
        situation_number_elem = situation.find('siri:SituationNumber', SIRI_NS)
        if situation_number_elem is None:
            logger.warning("[SiriSxAdapter] Skipping situation without SituationNumber")
            return None
        situation_number = situation_number_elem.text
        
        # Generate unique ID
        alert_id = self._make_unique_id(situation_number, source_name)
        
        # Parse ValidityPeriod(s) to create active_periods
        active_periods = []
        validity_periods = situation.findall('siri:ValidityPeriod', SIRI_NS)
        for validity_period in validity_periods:
            start_elem = validity_period.find('siri:StartTime', SIRI_NS)
            end_elem = validity_period.find('siri:EndTime', SIRI_NS)
            
            start_time = None
            end_time = None
            
            if start_elem is not None:
                try:
                    start_time = int(datetime.fromisoformat(
                        start_elem.text.replace('Z', '+00:00')
                    ).timestamp())
                except (ValueError, AttributeError) as e:
                    logger.warning(
                        f"[SiriSxAdapter] Failed to parse ValidityPeriod StartTime: {e}"
                    )
            
            if end_elem is not None:
                try:
                    end_dt = datetime.fromisoformat(
                        end_elem.text.replace('Z', '+00:00')
                    )
                    # If year is 2500, treat as unlimited end time (set to None)
                    if end_dt.year == 2500:
                        end_time = None
                    else:
                        end_time = int(end_dt.timestamp())
                except (ValueError, AttributeError) as e:
                    logger.warning(
                        f"[SiriSxAdapter] Failed to parse ValidityPeriod EndTime: {e}"
                    )
            
            active_periods.append({
                "start_time": start_time,
                "end_time": end_time,
            })
        
        # Parse translations from Summary and Detail elements on PtSituationElement level
        translations_dict = {}  # {language: {header: ..., description: ...}}
        info_link_element = None  # Will store the InfoLink element if found
        
        # Try to extract from PtSituationElement first
        summary_elements = situation.findall('siri:Summary', SIRI_NS)
        detail_elements = situation.findall('siri:Detail', SIRI_NS)
        description_elements = situation.findall('siri:Description', SIRI_NS)
        info_link_element = situation.find('siri:InfoLink', SIRI_NS)
        
        # If no Summary/Detail/Description found on PtSituationElement, try PassengerInformationAction fallback
        if not summary_elements and not detail_elements and not description_elements:
            # Find PassengerInformationAction elements
            publishing_actions_temp = situation.findall('.//siri:PublishingAction', SIRI_NS)
            
            # First, try to find one with Perspective="general"
            selected_action = None
            all_passenger_infos = []
            
            for pub_action in publishing_actions_temp:
                passenger_info = pub_action.find('siri:PassengerInformationAction', SIRI_NS)
                if passenger_info is not None:
                    all_passenger_infos.append(passenger_info)
                    perspectives = passenger_info.findall('siri:Perspective', SIRI_NS)
                    for perspective in perspectives:
                        if perspective.text == 'general':
                            selected_action = passenger_info
                            break
                    if selected_action is not None:
                        break  # Use first with "general" perspective
            
            # If no "general" perspective found, use first PassengerInformationAction
            if selected_action is None and all_passenger_infos:
                selected_action = all_passenger_infos[0]
            
            # Extract from PassengerInformationAction if found
            if selected_action is not None:
                # Try direct Summary/Detail/Description elements first
                summary_elements = selected_action.findall('siri:Summary', SIRI_NS)
                detail_elements = selected_action.findall('siri:Detail', SIRI_NS)
                description_elements = selected_action.findall('siri:Description', SIRI_NS)
                
                # Also try to get InfoLink from PassengerInformationAction
                if info_link_element is None:
                    info_link_element = selected_action.find('siri:InfoLink', SIRI_NS)
                
                # If still no content, try TextualContent fallback
                if not summary_elements and not detail_elements and not description_elements:
                    textual_contents = selected_action.findall('siri:TextualContent', SIRI_NS)
                    
                    # Find TextualContent with TextualContentSize="L", or use first
                    selected_textual_content = None
                    for tc in textual_contents:
                        size_elem = tc.find('siri:TextualContentSize', SIRI_NS)
                        if size_elem is not None and size_elem.text == 'L':
                            selected_textual_content = tc
                            break
                    
                    # If no "L" size found, use first textual content
                    if selected_textual_content is None and textual_contents:
                        selected_textual_content = textual_contents[0]
                    
                    # Extract from TextualContent
                    if selected_textual_content is not None:
                        summary_elements, detail_elements, description_elements = self._extract_from_textual_content(
                            selected_textual_content,
                            SIRI_NS
                        )
                        
                        # Also try to get InfoLink from TextualContent
                        if info_link_element is None:
                            info_link_element = selected_textual_content.find('siri:InfoLink', SIRI_NS)
        
        # Require at least Summary
        if not summary_elements:
            logger.warning(
                f"[SiriSxAdapter] Skipping situation {situation_number}: "
                f"No Summary element found (checked PtSituationElement, PassengerInformationAction, and TextualContent)"
            )
            return None
        
        # Extract Summary elements
        for summary_elem in summary_elements:
            lang = summary_elem.get('{http://www.w3.org/XML/1998/namespace}lang', 'de')
            lang = lang.lower()
            header = self._strip_html(summary_elem.text or "")
            
            if lang not in translations_dict:
                translations_dict[lang] = {'description_parts': []}
            translations_dict[lang]['header_text'] = header
        
        # Extract Detail elements and collect them for concatenation
        for detail_elem in detail_elements:
            lang = detail_elem.get('{http://www.w3.org/XML/1998/namespace}lang', 'de')
            lang = lang.lower()
            description = self._strip_html(detail_elem.text or "")
            
            if description:  # Only add non-empty descriptions
                if lang not in translations_dict:
                    translations_dict[lang] = {'description_parts': []}
                translations_dict[lang]['description_parts'].append(description)
        
        # Also extract Description elements (alternative to Detail) and collect them
        for desc_elem in description_elements:
            lang = desc_elem.get('{http://www.w3.org/XML/1998/namespace}lang', 'de')
            lang = lang.lower()
            description = self._strip_html(desc_elem.text or "")
            
            if description:  # Only add non-empty descriptions
                if lang not in translations_dict:
                    translations_dict[lang] = {'description_parts': []}
                translations_dict[lang]['description_parts'].append(description)
        
        # Extract URL from InfoLink if found
        url_value = None
        if info_link_element is not None:
            uri_elem = info_link_element.find('siri:Uri', SIRI_NS)
            if uri_elem is not None and uri_elem.text:
                url_value = uri_elem.text.strip()
        
        # Convert translations_dict to list format, joining description parts with space
        translations = []
        for lang, data in translations_dict.items():
            # Join all description parts with single space
            description_parts = data.get('description_parts', [])
            description_text = ' '.join(description_parts) if description_parts else None
            
            translations.append({
                "language": lang,
                "header_text": data.get('header_text'),
                "description_text": description_text,
                "url": url_value,
            })
        
        # Parse InformedEntities from Affects
        publishing_actions = situation.findall('.//siri:PublishingAction', SIRI_NS)
        informed_entities = self._extract_informed_entities(
            situation,
            publishing_actions,
            SIRI_NS
        )
        
        # Use unknown values for all mappings
        severity = "UNKNOWN_SEVERITY"
        cause = "UNKNOWN_CAUSE"
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
    
    def _strip_html(self, text: str) -> str:
        """
        Strip HTML tags and clean up text.
        
        Args:
            text: Text potentially containing HTML tags and special characters
            
        Returns:
            Text with HTML tags removed and cleaned
        """
        if not text:
            return ""
        
        # Remove HTML tags using regex
        clean_text = re.sub(r'<[^>]+>', '', text)
        # Replace common HTML entities
        clean_text = clean_text.replace('&lt;', '<')
        clean_text = clean_text.replace('&gt;', '>')
        clean_text = clean_text.replace('&amp;', '&')
        clean_text = clean_text.replace('&quot;', '"')
        clean_text = clean_text.replace('&apos;', "'")
        clean_text = clean_text.replace('&nbsp;', ' ')
        # Replace <br> variants with space
        clean_text = re.sub(r'&lt;br&gt;', ' ', clean_text, flags=re.IGNORECASE)
        
        # Remove special characters: \n, \r, \t
        clean_text = clean_text.replace('\n', ' ')
        clean_text = clean_text.replace('\r', ' ')
        clean_text = clean_text.replace('\t', ' ')
        
        # Replace multiple spaces with single space
        clean_text = re.sub(r' +', ' ', clean_text)
        
        return clean_text.strip()
    
    def _extract_from_textual_content(
        self,
        textual_content: ET.Element,
        SIRI_NS: dict[str, str]
    ) -> tuple[list[ET.Element], list[ET.Element], list[ET.Element]]:
        """
        Extract Summary, Detail, and Description elements from TextualContent.
        
        Args:
            textual_content: TextualContent XML element
            SIRI_NS: SIRI namespace dictionary
            
        Returns:
            Tuple of (summary_elements, detail_elements, description_elements)
        """
        summary_elements = []
        detail_elements = []  # Usually not in TextualContent
        description_elements = []
        
        # Extract from SummaryContent -> SummaryText
        summary_content = textual_content.find('siri:SummaryContent', SIRI_NS)
        if summary_content is not None:
            summary_elements = summary_content.findall('siri:SummaryText', SIRI_NS)
        
        # Extract from DescriptionContent -> DescriptionText
        description_content = textual_content.find('siri:DescriptionContent', SIRI_NS)
        if description_content is not None:
            description_elements = description_content.findall('siri:DescriptionText', SIRI_NS)
        
        # Also try ReasonContent, ConsequenceContent as alternative description sources
        if not description_elements:
            reason_content = textual_content.find('siri:ReasonContent', SIRI_NS)
            if reason_content is not None:
                description_elements = reason_content.findall('siri:ReasonText', SIRI_NS)
        
        if not description_elements:
            consequence_content = textual_content.find('siri:ConsequenceContent', SIRI_NS)
            if consequence_content is not None:
                description_elements = consequence_content.findall('siri:ConsequenceText', SIRI_NS)
        
        return summary_elements, detail_elements, description_elements
    
    def _matches_participant_filter(
        self,
        situation: ET.Element,
        SIRI_NS: dict[str, str]
    ) -> bool:
        """
        Check if a PtSituationElement matches the configured participant filter.
        
        Args:
            situation: PtSituationElement XML element
            SIRI_NS: SIRI namespace dictionary
            
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
        participant_ref_elem = situation.find('siri:ParticipantRef', SIRI_NS)
        participant_ref = participant_ref_elem.text.strip() if participant_ref_elem is not None and participant_ref_elem.text else None
        
        # Check if participant is in allowed list
        if participant_ref and participant_ref in allowed_participants:
            return True
        
        # Log filtered situations
        situation_number_elem = situation.find('siri:SituationNumber', SIRI_NS)
        situation_number = situation_number_elem.text if situation_number_elem is not None else "unknown"
        
        logger.debug(
            f"[SiriSxAdapter] Filtering out situation {situation_number}: "
            f"ParticipantRef '{participant_ref}' not in allowed list: {', '.join(allowed_participants)}"
        )
        
        return False
    
    def _is_in_publication_window(
        self,
        situation: ET.Element,
        current_timestamp: int,
        SIRI_NS: dict[str, str]
    ) -> bool:
        """
        Check if a situation is within its publication window.
        
        Also filters out situations whose publication window starts more than 30 days in the future.
        
        Args:
            situation: PtSituationElement XML element
            current_timestamp: Current Unix timestamp
            SIRI_NS: SIRI namespace dictionary
            
        Returns:
            True if situation is in publication window, False otherwise
        """
        publication_windows = situation.findall('siri:PublicationWindow', SIRI_NS)
        
        # If no publication windows, situation is valid
        if not publication_windows:
            return True
        
        # Maximum start time: 30 days in the future
        max_future_start = current_timestamp + (30 * 24 * 60 * 60)  # 30 days in seconds
        
        # Check if current time is within any publication window
        for pub_window in publication_windows:
            start_elem = pub_window.find('siri:StartTime', SIRI_NS)
            end_elem = pub_window.find('siri:EndTime', SIRI_NS)
            
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
                        f"[SiriSxAdapter] Failed to parse PublicationWindow times: {e}"
                    )
        
        return False
    
    def _extract_informed_entities(
        self,
        situation: ET.Element,
        publishing_actions: list[ET.Element],
        SIRI_NS: dict[str, str]
    ) -> list[dict[str, Any]]:
        """
        Extract informed entities from Affects sections.
        
        Args:
            situation: PtSituationElement XML element
            publishing_actions: List of PublishingAction elements
            SIRI_NS: SIRI namespace dictionary
            
        Returns:
            List of informed entity dictionaries
        """
        informed_entities = []
        
        for pub_action in publishing_actions:
            # Check both PublishAtScope and Consequences for Affects
            affects_elements = []
            
            publish_at_scope = pub_action.find('siri:PublishAtScope', SIRI_NS)
            if publish_at_scope is not None:
                affects_elem = publish_at_scope.find('siri:Affects', SIRI_NS)
                if affects_elem is not None:
                    affects_elements.append(affects_elem)
            
            # Also check Consequences (from situation level)
            consequences = situation.findall('.//siri:Consequence', SIRI_NS)
            for consequence in consequences:
                affects_elem = consequence.find('siri:Affects', SIRI_NS)
                if affects_elem is not None:
                    affects_elements.append(affects_elem)
            
            for affects in affects_elements:
                # Extract Networks (contains routes/lines and operators)
                networks = affects.findall('.//siri:AffectedNetwork', SIRI_NS)
                for network in networks:
                    affected_lines = network.findall('.//siri:AffectedLine', SIRI_NS)
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
                        operator_ref = affected_line.find('.//siri:OperatorRef', SIRI_NS)
                        if operator_ref is not None:
                            entity["agency_id"] = operator_ref.text
                        
                        # Extract LineRef (route_id)
                        line_ref = affected_line.find('siri:LineRef', SIRI_NS)
                        if line_ref is not None:
                            entity["route_id"] = line_ref.text
                        
                        informed_entities.append(entity)
                
                # Extract StopPlaces
                stop_places = affects.findall('.//siri:AffectedStopPlace', SIRI_NS)
                for stop_place in stop_places:
                    stop_place_ref = stop_place.find('siri:StopPlaceRef', SIRI_NS)
                    if stop_place_ref is not None:
                        # Also extract lines within this stop place
                        lines_in_stop = stop_place.findall('.//siri:AffectedLine', SIRI_NS)
                        
                        if lines_in_stop:
                            # Create entity for each line at this stop
                            for affected_line in lines_in_stop:
                                entity = {
                                    "agency_id": None,
                                    "route_id": None,
                                    "route_type": None,
                                    "stop_id": stop_place_ref.text,
                                    "trip_id": None,
                                    "direction_id": None,
                                }
                                
                                # Extract OperatorRef (agency_id)
                                operator_ref = affected_line.find('.//siri:OperatorRef', SIRI_NS)
                                if operator_ref is not None:
                                    entity["agency_id"] = operator_ref.text
                                
                                # Extract LineRef (route_id)
                                line_ref = affected_line.find('siri:LineRef', SIRI_NS)
                                if line_ref is not None:
                                    entity["route_id"] = line_ref.text
                                
                                informed_entities.append(entity)
                        else:
                            # Just the stop without specific lines
                            informed_entities.append({
                                "agency_id": None,
                                "route_id": None,
                                "route_type": None,
                                "stop_id": stop_place_ref.text,
                                "trip_id": None,
                                "direction_id": None,
                            })
        
        return informed_entities
