"""Transformer for SIRI-SX Swiss dialect service-alert payloads."""

from __future__ import annotations

import logging
import re
import time
from time import perf_counter
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Callable

from echogtfs.datasources.transformers.intf_service_alerts_transformer import (
    ServiceAlertsTransformerInterface,
)
from echogtfs.enum.gtfsrt import PeriodType

logger = logging.getLogger("uvicorn")


class SiriSxSwissServiceAlertsTransformer(ServiceAlertsTransformerInterface):
    """Transforms SIRI-SX Swiss XML into service-alert dictionaries."""

    def __init__(
        self,
        make_unique_id: Callable[[str, str], Any],
        filter_value: str | None = None,
    ):
        self._make_unique_id = make_unique_id
        self._filter_value = (filter_value or "").strip()
        self._siri_ns = {"siri": "http://www.siri.org.uk/siri"}
        self._runtime_duration_ms = 0.0

    def transform(self, raw_data: Any) -> list[dict[str, Any]]:
        self._runtime_duration_ms = 0.0
        start_time = perf_counter()
        root = raw_data["root"]
        source_name = raw_data["source_name"]

        situations = root.findall(".//siri:PtSituationElement", self._siri_ns)
        if not situations:
            self._runtime_duration_ms = (perf_counter() - start_time) * 1000
            return []

        alerts = []
        filtered_out_of_window = 0
        filtered_by_participant = 0
        current_timestamp = int(time.time())

        try:
            for situation in situations:
                try:
                    if not self._matches_participant_filter(situation):
                        filtered_by_participant += 1
                        continue

                    if not self._is_in_publication_window(situation, current_timestamp):
                        filtered_out_of_window += 1
                        continue

                    alert = self._parse_situation(situation, source_name)
                    if alert:
                        alerts.append(alert)
                except Exception as exc:
                    logger.error(
                        f"[SiriSxSwissServiceAlertsTransformer] Error processing situation: {exc}",
                        exc_info=True,
                    )

            logger.info(
                "[SiriSxSwissServiceAlertsTransformer] Processed %s alerts (filtered: %s participant, %s window)",
                len(alerts),
                filtered_by_participant,
                filtered_out_of_window,
            )

            return alerts
        finally:
            self._runtime_duration_ms = (perf_counter() - start_time) * 1000

    def get_runtime_duration_ms(self) -> float:
        return float(self._runtime_duration_ms)

    def _matches_participant_filter(self, situation: ET.Element) -> bool:
        if not self._filter_value:
            return True

        allowed_patterns = [
            participant.strip()
            for participant in self._filter_value.split(",")
            if participant.strip()
        ]

        participant_ref_elem = situation.find("siri:ParticipantRef", self._siri_ns)
        participant_ref = (
            participant_ref_elem.text.strip()
            if participant_ref_elem is not None and participant_ref_elem.text
            else None
        )

        if not participant_ref:
            return False

        return any(self._wildcard_matches(pattern, participant_ref) for pattern in allowed_patterns)

    @staticmethod
    def _wildcard_matches(pattern: str, value: str) -> bool:
        regex = re.escape(pattern).replace(r"\*", ".*")
        return bool(re.fullmatch(regex, value))

    def _is_in_publication_window(self, situation: ET.Element, current_timestamp: int) -> bool:
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
                        f"[SiriSxSwissServiceAlertsTransformer] Failed to parse PublicationWindow times: {exc}"
                    )

        return False

    def _parse_situation(self, situation: ET.Element, source_name: str) -> dict[str, Any] | None:
        situation_number_elem = situation.find("siri:SituationNumber", self._siri_ns)
        if situation_number_elem is None:
            logger.warning("[SiriSxSwissServiceAlertsTransformer] Skipping situation without SituationNumber")
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
                except (ValueError, AttributeError):
                    pass

            if end_elem is not None:
                try:
                    end_time = int(
                        datetime.fromisoformat(end_elem.text.replace("Z", "+00:00")).timestamp()
                    )
                except (ValueError, AttributeError):
                    pass

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
                except (ValueError, AttributeError):
                    pass

            if end_elem is not None:
                try:
                    end_time = int(
                        datetime.fromisoformat(end_elem.text.replace("Z", "+00:00")).timestamp()
                    )
                except (ValueError, AttributeError):
                    pass

            active_periods.append(
                {
                    "period_type": PeriodType.COMMUNICATION_PERIOD,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )

        translations = self._extract_translations(situation)
        if not translations:
            return None

        informed_entities = self._extract_informed_entities(situation)

        severity_elem = situation.find("siri:Severity", self._siri_ns)
        alert_cause_elem = situation.find("siri:AlertCause", self._siri_ns)

        return {
            "id": alert_id,
            "cause": self._map_cause_swiss(alert_cause_elem.text if alert_cause_elem is not None else None),
            "effect": "UNKNOWN_EFFECT",
            "severity_level": self._map_severity_swiss(severity_elem.text if severity_elem is not None else None),
            "is_active": True,
            "translations": translations,
            "active_periods": active_periods,
            "informed_entities": informed_entities,
        }

    def _extract_translations(self, situation: ET.Element) -> list[dict[str, Any]]:
        translations_dict = {}

        publishing_actions = situation.findall(".//siri:PublishingAction", self._siri_ns)
        passenger_infos = []
        for pub_action in publishing_actions:
            passenger_info = pub_action.find("siri:PassengerInformationAction", self._siri_ns)
            if passenger_info is not None:
                passenger_infos.append(passenger_info)

        selected_passenger_info = None
        for passenger_info in passenger_infos:
            perspectives = passenger_info.findall("siri:Perspective", self._siri_ns)
            for perspective in perspectives:
                if perspective.text == "general":
                    selected_passenger_info = passenger_info
                    break

            if selected_passenger_info is not None:
                break

        if selected_passenger_info is None and passenger_infos:
            selected_passenger_info = passenger_infos[0]

        textual_contents = []
        if selected_passenger_info is not None:
            textual_contents = selected_passenger_info.findall("siri:TextualContent", self._siri_ns)

        selected_textual_content = None
        for textual_content in textual_contents:
            size_elem = textual_content.find("siri:TextualContentSize", self._siri_ns)
            if size_elem is not None and size_elem.text == "L":
                selected_textual_content = textual_content
                break

        if selected_textual_content is None and textual_contents:
            selected_textual_content = textual_contents[0]

        if selected_textual_content is not None:
            summary_content = selected_textual_content.find("siri:SummaryContent", self._siri_ns)
            if summary_content is not None:
                summary_texts = summary_content.findall("siri:SummaryText", self._siri_ns)
                for summary_text in summary_texts:
                    lang = summary_text.get("{http://www.w3.org/XML/1998/namespace}lang", "de").lower()
                    if lang not in translations_dict:
                        translations_dict[lang] = {"description_parts": []}

                    translations_dict[lang]["header_text"] = summary_text.text or ""

            content_sections = [
                ("siri:ReasonContent", "siri:ReasonText"),
                ("siri:DescriptionContent", "siri:DescriptionText"),
                ("siri:ConsequenceContent", "siri:ConsequenceText"),
                ("siri:RecommendationContent", "siri:RecommendationText"),
                ("siri:DurationContent", "siri:DurationText"),
                ("siri:RemarkContent", "siri:Remark"),
            ]

            for content_name, text_name in content_sections:
                content = selected_textual_content.find(content_name, self._siri_ns)
                if content is None:
                    continue

                text_elements = content.findall(text_name, self._siri_ns)
                for text_elem in text_elements:
                    text = text_elem.text or ""
                    if not text.strip():
                        continue

                    lang = text_elem.get("{http://www.w3.org/XML/1998/namespace}lang", "de").lower()
                    if lang not in translations_dict:
                        translations_dict[lang] = {"description_parts": []}

                    translations_dict[lang]["description_parts"].append(text)

            info_link = selected_textual_content.find("siri:InfoLink", self._siri_ns)
            if info_link is not None:
                uri_elem = info_link.find("siri:Uri", self._siri_ns)
                if uri_elem is not None and uri_elem.text:
                    for lang in translations_dict:
                        translations_dict[lang]["url"] = uri_elem.text

        translations = []
        for lang, data in translations_dict.items():
            description_parts = data.get("description_parts", [])
            translations.append(
                {
                    "language": lang,
                    "header_text": data.get("header_text"),
                    "description_text": "\n\n".join(description_parts) if description_parts else None,
                    "url": data.get("url"),
                }
            )

        has_meaningful_text = any(
            translation.get("header_text") or translation.get("description_text")
            for translation in translations
        )

        if not has_meaningful_text:
            return []

        return translations

    def _extract_informed_entities(self, situation: ET.Element) -> list[dict[str, Any]]:
        informed_entities = []
        affects_elements = []

        publishing_actions = situation.findall(".//siri:PublishingAction", self._siri_ns)
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
            if stop_place_ref is None or not stop_place_ref.text:
                continue

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
            if stop_point_ref is None or not stop_point_ref.text:
                continue

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
        if vehicle_journeys_container is None:
            return

        vehicle_journeys = vehicle_journeys_container.findall(
            "siri:AffectedVehicleJourney", self._siri_ns
        )

        for vehicle_journey in vehicle_journeys:
            journey_ref = vehicle_journey.find("siri:VehicleJourneyRef", self._siri_ns)

            if journey_ref is None or not journey_ref.text:
                journey_ref = vehicle_journey.find("siri:DatedVehicleJourneyRef", self._siri_ns)

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

                    for affected_stop_point in affected_stop_points:
                        stop_point_ref = affected_stop_point.find("siri:StopPointRef", self._siri_ns)
                        if stop_point_ref is not None and stop_point_ref.text:
                            stop_ids.append(stop_point_ref.text)

                        stop_place_ref = affected_stop_point.find("siri:StopPlaceRef", self._siri_ns)
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

    def _map_severity_swiss(self, siri_severity: str | None) -> str:
        if not siri_severity:
            return "UNKNOWN_SEVERITY"

        severity_mapping = {
            "slight": "INFO",
            "normal": "WARNING",
            "severe": "SEVERE",
            "verysevere": "SEVERE",
            "noimpact": "INFO",
        }

        return severity_mapping.get(siri_severity.lower(), "UNKNOWN_SEVERITY")

    def _map_cause_swiss(self, siri_cause: str | None) -> str:
        if not siri_cause:
            return "UNKNOWN_CAUSE"

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
        
        return cause_mapping.get(siri_cause.lower(), "UNKNOWN_CAUSE")
