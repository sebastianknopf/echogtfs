"""Transformer for GTFS-Realtime service-alert payloads."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from echogtfs.datasources.transformers.intf_service_alerts_transformer import (
    ServiceAlertsTransformerInterface,
)
from echogtfs.enum.gtfsrt import PeriodType

logger = logging.getLogger("uvicorn")


class GtfsRtServiceAlertsTransformer(ServiceAlertsTransformerInterface):
    """Transforms parsed GTFS-RT feed entities into service-alert dictionaries."""

    def __init__(self, make_unique_id: Callable[[str, str], Any]):
        self._make_unique_id = make_unique_id

    def transform(self, raw_data: Any) -> list[dict[str, Any]]:
        feed = raw_data["feed"]
        source_name = raw_data["source_name"]

        alerts = []
        filtered_not_yet_valid = 0
        filtered_expired = 0

        for entity in feed.entity:
            if not entity.HasField("alert"):
                continue

            alert = entity.alert
            alert_id = self._make_unique_id(entity.id, source_name)

            cause = self._map_cause(alert.cause) if alert.HasField("cause") else "UNKNOWN_CAUSE"
            effect = self._map_effect(alert.effect) if alert.HasField("effect") else "UNKNOWN_EFFECT"
            severity = (
                self._map_severity(alert.severity_level)
                if alert.HasField("severity_level")
                else "UNKNOWN_SEVERITY"
            )

            translations = []
            if alert.HasField("header_text"):
                for translation in alert.header_text.translation:
                    language = translation.language if translation.HasField("language") else "de-DE"
                    header = translation.text if translation.HasField("text") else None

                    description = None
                    if alert.HasField("description_text"):
                        for desc_trans in alert.description_text.translation:
                            if (
                                desc_trans.HasField("language")
                                and desc_trans.language == language
                            ) or (
                                not desc_trans.HasField("language") and language == "de-DE"
                            ):
                                description = (
                                    desc_trans.text if desc_trans.HasField("text") else None
                                )
                                break

                    url = None
                    if alert.HasField("url"):
                        for url_trans in alert.url.translation:
                            if (
                                url_trans.HasField("language") and url_trans.language == language
                            ) or (
                                not url_trans.HasField("language") and language == "de-DE"
                            ):
                                url = url_trans.text if url_trans.HasField("text") else None
                                break

                    translations.append(
                        {
                            "language": language,
                            "header_text": header,
                            "description_text": description,
                            "url": url,
                        }
                    )

            if not translations:
                translations.append(
                    {
                        "language": "de-DE",
                        "header_text": "Service Alert",
                        "description_text": None,
                        "url": None,
                    }
                )

            active_periods = []
            if hasattr(alert, "impact_period"):
                for period in alert.impact_period:
                    active_periods.append(
                        {
                            "period_type": PeriodType.IMPACT_PERIOD,
                            "start_time": period.start if period.HasField("start") else None,
                            "end_time": period.end if period.HasField("end") else None,
                        }
                    )

            if hasattr(alert, "communication_period"):
                for period in alert.communication_period:
                    active_periods.append(
                        {
                            "period_type": PeriodType.COMMUNICATION_PERIOD,
                            "start_time": period.start if period.HasField("start") else None,
                            "end_time": period.end if period.HasField("end") else None,
                        }
                    )

            if not active_periods and alert.active_period:
                for period in alert.active_period:
                    active_periods.append(
                        {
                            "period_type": PeriodType.IMPACT_PERIOD,
                            "start_time": period.start if period.HasField("start") else None,
                            "end_time": period.end if period.HasField("end") else None,
                        }
                    )

            if active_periods:
                current_timestamp = int(time.time())
                start_times = [p["start_time"] for p in active_periods if p["start_time"] is not None]
                if start_times:
                    earliest_start = min(start_times)
                    one_month = 30 * 24 * 60 * 60
                    if earliest_start > current_timestamp + one_month:
                        filtered_not_yet_valid += 1
                        continue

                end_times = [p["end_time"] for p in active_periods if p["end_time"] is not None]
                if end_times and max(end_times) < current_timestamp:
                    filtered_expired += 1
                    continue

            informed_entities = []
            for entity_selector in alert.informed_entity:
                informed_entities.append(
                    {
                        "agency_id": entity_selector.agency_id
                        if entity_selector.HasField("agency_id")
                        else None,
                        "route_id": entity_selector.route_id
                        if entity_selector.HasField("route_id")
                        else None,
                        "route_type": entity_selector.route_type
                        if entity_selector.HasField("route_type")
                        else None,
                        "stop_id": entity_selector.stop_id
                        if entity_selector.HasField("stop_id")
                        else None,
                        "trip_id": entity_selector.trip.trip_id
                        if entity_selector.HasField("trip")
                        and entity_selector.trip.HasField("trip_id")
                        else None,
                        "direction_id": entity_selector.trip.direction_id
                        if entity_selector.HasField("trip")
                        and entity_selector.trip.HasField("direction_id")
                        else None,
                    }
                )

            alerts.append(
                {
                    "id": alert_id,
                    "cause": cause,
                    "effect": effect,
                    "severity_level": severity,
                    "is_active": True,
                    "translations": translations,
                    "active_periods": active_periods,
                    "informed_entities": informed_entities,
                }
            )

        total_filtered = filtered_not_yet_valid + filtered_expired
        if total_filtered > 0:
            logger.info(
                "[GtfsRtTransformer] Filtered %s alerts: %s not yet valid, %s expired",
                total_filtered,
                filtered_not_yet_valid,
                filtered_expired,
            )

        logger.info("[GtfsRtTransformer] Transformed %s valid alerts", len(alerts))

        return alerts

    def _map_cause(self, gtfs_cause: int) -> str:
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
        severity_mapping = {
            1: "UNKNOWN_SEVERITY",
            2: "INFO",
            3: "WARNING",
            4: "SEVERE",
        }
        
        return severity_mapping.get(gtfs_severity, "UNKNOWN_SEVERITY")
