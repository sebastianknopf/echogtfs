"""Shared SIRI-SX transformer used by SIRI-Lite and SIRI-SX datasources."""

from __future__ import annotations

import locale
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Callable

from echogtfs.datasources.transformers.intf_service_alerts_transformer import (
    ServiceAlertsTransformerInterface,
)
from echogtfs.enum.gtfsrt import PeriodType

logger = logging.getLogger("uvicorn")


class SiriSxServiceAlertsTransformer(ServiceAlertsTransformerInterface):
    """Transforms SIRI-SX payload XML into service-alert dictionaries."""

    def __init__(
        self,
        make_unique_id: Callable[[str, str], Any],
        filter_value: str | None = None,
    ):
        self._make_unique_id = make_unique_id
        self._filter_value = (filter_value or "").strip()
        self._siri_ns = {"siri": "http://www.siri.org.uk/siri"}

    def transform(self, raw_data: Any) -> list[dict[str, Any]]:
        """Transform SIRI-SX XML root to internal service-alert dictionaries."""
        root = raw_data["root"]
        source_name = raw_data["source_name"]

        situations = root.findall(".//siri:PtSituationElement", self._siri_ns)
        if not situations:
            return []

        alerts = []
        filtered_out_of_window = 0
        filtered_by_participant = 0
        current_timestamp = int(time.time())

        for situation in situations:
            try:
                if not self._matches_participant_filter(situation):
                    filtered_by_participant += 1
                    continue

                if not self._is_in_publication_window(situation, current_timestamp):
                    filtered_out_of_window += 1
                    continue

                alert = self._parse_situation_element_sirisx(
                    situation,
                    source_name,
                    current_timestamp,
                )

                if alert:
                    alerts.append(alert)
            except Exception as exc:
                situation_number_elem = situation.find("siri:SituationNumber", self._siri_ns)
                situation_number = (
                    situation_number_elem.text if situation_number_elem is not None else "unknown"
                )

                logger.error(
                    f"[SiriSxTransformer] Error parsing situation {situation_number}: {exc}"
                )

        logger.info(
            "[SiriSxTransformer] Processed %s alerts (filtered: %s participant, %s window)",
            len(alerts),
            filtered_by_participant,
            filtered_out_of_window,
        )

        return alerts

    def _parse_situation_element_sirisx(
        self,
        situation: ET.Element,
        source_name: str,
        current_timestamp: int,
    ) -> dict[str, Any] | None:
        situation_number_elem = situation.find("siri:SituationNumber", self._siri_ns)
        if situation_number_elem is None:
            logger.warning("[SiriSxTransformer] Skipping situation without SituationNumber")
            return None
        
        situation_number = situation_number_elem.text

        alert_id = self._make_unique_id(situation_number, source_name)

        active_periods = []
        validity_periods = situation.findall("siri:ValidityPeriod", self._siri_ns)
        for validity_period in validity_periods:
            start_elem = validity_period.find("siri:StartTime", self._siri_ns)
            end_elem = validity_period.find("siri:EndTime", self._siri_ns)

            start_time = None
            end_time = None

            if start_elem is not None:
                try:
                    start_time = int(
                        datetime.fromisoformat(start_elem.text.replace("Z", "+00:00")).timestamp()
                    )
                except (ValueError, AttributeError) as exc:
                    logger.warning(
                        f"[SiriSxTransformer] Failed to parse ValidityPeriod StartTime: {exc}"
                    )

            if end_elem is not None:
                try:
                    end_dt = datetime.fromisoformat(end_elem.text.replace("Z", "+00:00"))
                    end_time = None if end_dt.year == 2500 else int(end_dt.timestamp())
                except (ValueError, AttributeError) as exc:
                    logger.warning(
                        f"[SiriSxTransformer] Failed to parse ValidityPeriod EndTime: {exc}"
                    )

            active_periods.append(
                {
                    "period_type": PeriodType.IMPACT_PERIOD,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )

        publication_windows = situation.findall("siri:PublicationWindow", self._siri_ns)
        for pub_window in publication_windows:
            start_elem = pub_window.find("siri:StartTime", self._siri_ns)
            end_elem = pub_window.find("siri:EndTime", self._siri_ns)

            start_time = None
            end_time = None

            if start_elem is not None:
                try:
                    start_time = int(
                        datetime.fromisoformat(start_elem.text.replace("Z", "+00:00")).timestamp()
                    )
                except (ValueError, AttributeError) as exc:
                    logger.warning(
                        f"[SiriSxTransformer] Failed to parse PublicationWindow StartTime: {exc}"
                    )

            if end_elem is not None:
                try:
                    end_dt = datetime.fromisoformat(end_elem.text.replace("Z", "+00:00"))
                    end_time = None if end_dt.year == 2500 else int(end_dt.timestamp())
                except (ValueError, AttributeError) as exc:
                    logger.warning(
                        f"[SiriSxTransformer] Failed to parse PublicationWindow EndTime: {exc}"
                    )

            active_periods.append(
                {
                    "period_type": PeriodType.COMMUNICATION_PERIOD,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )

        translations_dict = {}
        info_link_element = None

        summary_elements = situation.findall("siri:Summary", self._siri_ns)
        detail_elements = situation.findall("siri:Detail", self._siri_ns)
        description_elements = situation.findall("siri:Description", self._siri_ns)
        info_link_element = situation.find("siri:InfoLink", self._siri_ns)

        if not summary_elements and not detail_elements and not description_elements:
            publishing_actions_temp = situation.findall(".//siri:PublishingAction", self._siri_ns)
            selected_action = None
            all_passenger_infos = []

            for pub_action in publishing_actions_temp:
                passenger_info = pub_action.find("siri:PassengerInformationAction", self._siri_ns)
                if passenger_info is not None:
                    all_passenger_infos.append(passenger_info)
                    perspectives = passenger_info.findall("siri:Perspective", self._siri_ns)
                    
                    for perspective in perspectives:
                        if perspective.text == "general":
                            selected_action = passenger_info
                            break
                    
                    if selected_action is not None:
                        break

            if selected_action is None and all_passenger_infos:
                selected_action = all_passenger_infos[0]

            if selected_action is not None:
                summary_elements = selected_action.findall("siri:Summary", self._siri_ns)
                detail_elements = selected_action.findall("siri:Detail", self._siri_ns)
                description_elements = selected_action.findall("siri:Description", self._siri_ns)

                if info_link_element is None:
                    info_link_element = selected_action.find("siri:InfoLink", self._siri_ns)

                if not summary_elements and not detail_elements and not description_elements:
                    textual_contents = selected_action.findall("siri:TextualContent", self._siri_ns)
                    selected_textual_content = None
                    for tc in textual_contents:
                        size_elem = tc.find("siri:TextualContentSize", self._siri_ns)
                        
                        if size_elem is not None and size_elem.text == "L":
                            selected_textual_content = tc
                            break

                    if selected_textual_content is None and textual_contents:
                        selected_textual_content = textual_contents[0]

                    if selected_textual_content is not None:
                        (
                            summary_elements,
                            detail_elements,
                            description_elements,
                        ) = self._extract_from_textual_content(selected_textual_content)

                        if info_link_element is None:
                            info_link_element = selected_textual_content.find(
                                "siri:InfoLink", self._siri_ns
                            )

        if not summary_elements:
            logger.warning(
                "[SiriSxTransformer] Skipping situation %s: no summary available",
                situation_number,
            )

            return None

        for summary_elem in summary_elements:
            lang = self._get_language_with_fallback(summary_elem, situation)
            header = self._strip_html(summary_elem.text or "")
            
            if lang not in translations_dict:
                translations_dict[lang] = {"description_parts": []}
            
            translations_dict[lang]["header_text"] = header

        for detail_elem in detail_elements:
            lang = self._get_language_with_fallback(detail_elem, situation)
            description = self._strip_html(detail_elem.text or "")
            
            if description:
                if lang not in translations_dict:
                    translations_dict[lang] = {"description_parts": []}
                
                translations_dict[lang]["description_parts"].append(description)

        for desc_elem in description_elements:
            lang = self._get_language_with_fallback(desc_elem, situation)
            description = self._strip_html(desc_elem.text or "")
            
            if description:
                if lang not in translations_dict:
                    translations_dict[lang] = {"description_parts": []}
                
                translations_dict[lang]["description_parts"].append(description)

        url_value = None
        if info_link_element is not None:
            uri_elem = info_link_element.find("siri:Uri", self._siri_ns)
            if uri_elem is not None and uri_elem.text:
                url_value = uri_elem.text.strip()

        translations = []
        for lang, data in translations_dict.items():
            description_parts = data.get("description_parts", [])
            description_text = " ".join(description_parts) if description_parts else None
            translations.append(
                {
                    "language": lang,
                    "header_text": data.get("header_text"),
                    "description_text": description_text,
                    "url": url_value,
                }
            )

        publishing_actions = situation.findall(".//siri:PublishingAction", self._siri_ns)
        informed_entities = self._extract_informed_entities(situation, publishing_actions)

        return {
            "id": alert_id,
            "cause": "UNKNOWN_CAUSE",
            "effect": "UNKNOWN_EFFECT",
            "severity_level": "UNKNOWN_SEVERITY",
            "is_active": True,
            "translations": translations,
            "active_periods": active_periods,
            "informed_entities": informed_entities,
        }

    def _strip_html(self, text: str) -> str:
        if not text:
            return ""
        
        clean_text = re.sub(r"<[^>]+>", "", text)
        clean_text = clean_text.replace("&lt;", "<")
        clean_text = clean_text.replace("&gt;", ">")
        clean_text = clean_text.replace("&amp;", "&")
        clean_text = clean_text.replace("&quot;", '"')
        clean_text = clean_text.replace("&apos;", "'")
        clean_text = clean_text.replace("&nbsp;", " ")
        clean_text = re.sub(r"&lt;br&gt;", " ", clean_text, flags=re.IGNORECASE)
        clean_text = clean_text.replace("\n", " ")
        clean_text = clean_text.replace("\r", " ")
        clean_text = clean_text.replace("\t", " ")
        clean_text = re.sub(r" +", " ", clean_text)

        return clean_text.strip()

    def _extract_from_textual_content(
        self,
        textual_content: ET.Element,
    ) -> tuple[list[ET.Element], list[ET.Element], list[ET.Element]]:
        summary_elements = []
        detail_elements = []
        description_elements = []

        summary_content = textual_content.find("siri:SummaryContent", self._siri_ns)
        if summary_content is not None:
            summary_elements = summary_content.findall("siri:SummaryText", self._siri_ns)

        description_content = textual_content.find("siri:DescriptionContent", self._siri_ns)
        if description_content is not None:
            description_elements = description_content.findall(
                "siri:DescriptionText", self._siri_ns
            )

        if not description_elements:
            reason_content = textual_content.find("siri:ReasonContent", self._siri_ns)
            if reason_content is not None:
                description_elements = reason_content.findall("siri:ReasonText", self._siri_ns)

        if not description_elements:
            consequence_content = textual_content.find("siri:ConsequenceContent", self._siri_ns)
            if consequence_content is not None:
                description_elements = consequence_content.findall(
                    "siri:ConsequenceText", self._siri_ns
                )

        return summary_elements, detail_elements, description_elements

    def _matches_participant_filter(self, situation: ET.Element) -> bool:
        if not self._filter_value:
            return True

        allowed_participants = {
            participant.strip()
            for participant in self._filter_value.split(",")
            if participant.strip()
        }

        participant_ref_elem = situation.find("siri:ParticipantRef", self._siri_ns)
        participant_ref = (
            participant_ref_elem.text.strip()
            if participant_ref_elem is not None and participant_ref_elem.text
            else None
        )

        return bool(participant_ref and participant_ref in allowed_participants)

    def _is_in_publication_window(
        self,
        situation: ET.Element,
        current_timestamp: int,
    ) -> bool:
        publication_windows = situation.findall("siri:PublicationWindow", self._siri_ns)
        if not publication_windows:
            return True

        max_future_start = current_timestamp + (30 * 24 * 60 * 60)

        for pub_window in publication_windows:
            start_elem = pub_window.find("siri:StartTime", self._siri_ns)
            end_elem = pub_window.find("siri:EndTime", self._siri_ns)

            if start_elem is not None and end_elem is not None:
                try:
                    start_time = int(
                        datetime.fromisoformat(start_elem.text.replace("Z", "+00:00")).timestamp()
                    )
                    end_time = int(
                        datetime.fromisoformat(end_elem.text.replace("Z", "+00:00")).timestamp()
                    )

                    if start_time > max_future_start:
                        continue

                    if start_time <= current_timestamp <= end_time:
                        return True

                    if start_time > current_timestamp and start_time <= max_future_start:
                        return True
                except (ValueError, AttributeError) as exc:
                    logger.warning(
                        f"[SiriSxTransformer] Failed to parse PublicationWindow times: {exc}"
                    )

        return False

    def _get_language_with_fallback(
        self,
        text_element: ET.Element,
        situation_element: ET.Element,
    ) -> str:
        lang = text_element.get("{http://www.w3.org/XML/1998/namespace}lang")
        if lang:
            return lang.lower()

        language_elem = situation_element.find("siri:Language", self._siri_ns)
        if language_elem is not None and language_elem.text:
            return language_elem.text.lower()

        try:
            system_locale = locale.getdefaultlocale()
            if system_locale and system_locale[0]:
                return system_locale[0].split("_")[0].lower()
        except Exception:
            pass

        return "de"

    def _extract_informed_entities(
        self,
        situation: ET.Element,
        publishing_actions: list[ET.Element],
    ) -> list[dict[str, Any]]:
        informed_entities = []
        affects_elements = []

        for pub_action in publishing_actions:
            publish_at_scope = pub_action.find("siri:PublishAtScope", self._siri_ns)
            if publish_at_scope is not None:
                affects_elem = publish_at_scope.find("siri:Affects", self._siri_ns)
                if affects_elem is not None:
                    affects_elements.append(affects_elem)

        if not affects_elements:
            consequences = situation.findall(".//siri:Consequence", self._siri_ns)
            for consequence in consequences:
                affects_elem = consequence.find("siri:Affects", self._siri_ns)
                if affects_elem is not None:
                    affects_elements.append(affects_elem)

        if not affects_elements:
            direct_affects = situation.find("siri:Affects", self._siri_ns)
            if direct_affects is not None:
                affects_elements.append(direct_affects)

        for affects in affects_elements:
            self._extract_entities_from_affects(affects, informed_entities)

        return informed_entities

    def _extract_entities_from_affects(
        self,
        affects: ET.Element,
        informed_entities: list[dict[str, Any]],
    ) -> None:
        networks = affects.findall(".//siri:AffectedNetwork", self._siri_ns)
        for network in networks:
            affected_lines = network.findall(".//siri:AffectedLine", self._siri_ns)
            for affected_line in affected_lines:
                entity = {
                    "agency_id": None,
                    "route_id": None,
                    "route_type": None,
                    "stop_id": None,
                    "trip_id": None,
                    "direction_id": None,
                }

                operator_ref = affected_line.find(".//siri:OperatorRef", self._siri_ns)
                if operator_ref is not None and operator_ref.text:
                    entity["agency_id"] = operator_ref.text

                line_ref = affected_line.find("siri:LineRef", self._siri_ns)
                if line_ref is not None and line_ref.text:
                    entity["route_id"] = line_ref.text

                informed_entities.append(entity)

        stop_places = affects.findall(".//siri:AffectedStopPlace", self._siri_ns)
        for stop_place in stop_places:
            stop_place_ref = stop_place.find("siri:StopPlaceRef", self._siri_ns)
            if stop_place_ref is not None and stop_place_ref.text:
                lines_in_stop = stop_place.findall(".//siri:AffectedLine", self._siri_ns)

                if lines_in_stop:
                    for affected_line in lines_in_stop:
                        entity = {
                            "agency_id": None,
                            "route_id": None,
                            "route_type": None,
                            "stop_id": stop_place_ref.text,
                            "trip_id": None,
                            "direction_id": None,
                        }

                        operator_ref = affected_line.find(".//siri:OperatorRef", self._siri_ns)
                        if operator_ref is not None and operator_ref.text:
                            entity["agency_id"] = operator_ref.text

                        line_ref = affected_line.find("siri:LineRef", self._siri_ns)
                        if line_ref is not None and line_ref.text:
                            entity["route_id"] = line_ref.text

                        informed_entities.append(entity)
                else:
                    informed_entities.append(
                        {
                            "agency_id": None,
                            "route_id": None,
                            "route_type": None,
                            "stop_id": stop_place_ref.text,
                            "trip_id": None,
                            "direction_id": None,
                        }
                    )

        stop_points = affects.findall(".//siri:AffectedStopPoint", self._siri_ns)
        for stop_point in stop_points:
            stop_point_ref = stop_point.find("siri:StopPointRef", self._siri_ns)
            if stop_point_ref is not None and stop_point_ref.text:
                lines_in_stop = stop_point.findall(".//siri:AffectedLine", self._siri_ns)

                if lines_in_stop:
                    for affected_line in lines_in_stop:
                        entity = {
                            "agency_id": None,
                            "route_id": None,
                            "route_type": None,
                            "stop_id": stop_point_ref.text,
                            "trip_id": None,
                            "direction_id": None,
                        }

                        operator_ref = affected_line.find(".//siri:OperatorRef", self._siri_ns)
                        if operator_ref is not None and operator_ref.text:
                            entity["agency_id"] = operator_ref.text

                        line_ref = affected_line.find("siri:LineRef", self._siri_ns)
                        if line_ref is not None and line_ref.text:
                            entity["route_id"] = line_ref.text

                        informed_entities.append(entity)
                else:
                    informed_entities.append(
                        {
                            "agency_id": None,
                            "route_id": None,
                            "route_type": None,
                            "stop_id": stop_point_ref.text,
                            "trip_id": None,
                            "direction_id": None,
                        }
                    )

        vehicle_journeys_container = affects.find("siri:VehicleJourneys", self._siri_ns)
        if vehicle_journeys_container is not None:
            vehicle_journeys = vehicle_journeys_container.findall(
                "siri:AffectedVehicleJourney", self._siri_ns
            )

            for vehicle_journey in vehicle_journeys:
                journey_ref = vehicle_journey.find("siri:VehicleJourneyRef", self._siri_ns)
                if journey_ref is None or not journey_ref.text:
                    journey_ref = vehicle_journey.find(
                        "siri:DatedVehicleJourneyRef", self._siri_ns
                    )
                    
                if journey_ref is None or not journey_ref.text:
                    continue

                trip_id = journey_ref.text

                agency_id = None
                operator = vehicle_journey.find("siri:Operator", self._siri_ns)
                if operator is not None:
                    operator_ref = operator.find("siri:OperatorRef", self._siri_ns)
                    if operator_ref is not None and operator_ref.text:
                        agency_id = operator_ref.text

                stop_ids = []
                route = vehicle_journey.find("siri:Route", self._siri_ns)
                if route is not None:
                    stop_points_container = route.find("siri:StopPoints", self._siri_ns)
                    if stop_points_container is not None:
                        affected_stop_points = stop_points_container.findall(
                            "siri:AffectedStopPoint", self._siri_ns
                        )
                        for asp in affected_stop_points:
                            stop_point_ref = asp.find("siri:StopPointRef", self._siri_ns)
                            if stop_point_ref is not None and stop_point_ref.text:
                                stop_ids.append(stop_point_ref.text)
                            stop_place_ref = asp.find("siri:StopPlaceRef", self._siri_ns)
                            if stop_place_ref is not None and stop_place_ref.text:
                                stop_ids.append(stop_place_ref.text)

                if stop_ids:
                    for stop_id in stop_ids:
                        informed_entities.append(
                            {
                                "agency_id": agency_id,
                                "route_id": None,
                                "route_type": None,
                                "stop_id": stop_id,
                                "trip_id": trip_id,
                                "direction_id": None,
                                "is_valid": False,
                            }
                        )
                else:
                    informed_entities.append(
                        {
                            "agency_id": agency_id,
                            "route_id": None,
                            "route_type": None,
                            "stop_id": None,
                            "trip_id": trip_id,
                            "direction_id": None,
                            "is_valid": False,
                        }
                    )
