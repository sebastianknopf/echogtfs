"""SIRI-VM transformer for vehicle-position payloads."""

from __future__ import annotations

import logging
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

from echogtfs.enum.gtfsrt import CongestionLevel, VehicleStopStatus, WheelchairAccessible
from echogtfs.datasources.transformers.intf_vehicle_positions_transformer import (
    VehiclePositionsTransformerInterface,
)

logger = logging.getLogger("uvicorn")


class SiriVmVehiclePositionsTransformer(VehiclePositionsTransformerInterface):
    """Transforms SIRI-VM XML payloads into vehicle-position dictionaries."""

    def __init__(self, filter_value: str | None = None):
        self._filter_value = (filter_value or "").strip()
        self._siri_ns = {"siri": "http://www.siri.org.uk/siri"}
        self._runtime_duration_ms = 0.0

    def transform(self, raw_data: Any) -> list[dict[str, Any]]:
        """Transform SIRI-VM XML root to internal vehicle-position dictionaries."""
        self._runtime_duration_ms = 0.0
        start_time = perf_counter()
        root = raw_data["root"]

        activities = root.findall(".//siri:VehicleActivity", self._siri_ns)
        if not activities:
            self._runtime_duration_ms = (perf_counter() - start_time) * 1000
            return []

        positions: list[dict[str, Any]] = []
        filtered_invalid = 0

        try:
            for activity in activities:
                try:
                    vehicle_position = self._parse_vehicle_activity(activity)
                    if vehicle_position is None:
                        filtered_invalid += 1
                        continue

                    positions.append(vehicle_position)
                except Exception as exc:
                    vehicle_ref = self._get_text(
                        activity.find(
                            "siri:MonitoredVehicleJourney/siri:VehicleRef",
                            self._siri_ns,
                        )
                    ) or "unknown"
                    logger.error(
                        "[SiriVmVehiclePositionsTransformer] Error parsing vehicle activity %s: %s",
                        vehicle_ref,
                        exc,
                    )

            logger.info(
                "[SiriVmVehiclePositionsTransformer] Processed %s vehicle positions (filtered: %s invalid)",
                len(positions),
                filtered_invalid,
            )

            return positions
        finally:
            self._runtime_duration_ms = (perf_counter() - start_time) * 1000

    def get_runtime_duration_ms(self) -> float:
        return float(self._runtime_duration_ms)

    def _parse_vehicle_activity(
        self,
        activity: ET.Element,
    ) -> dict[str, Any] | None:
        valid_until = self._parse_datetime(
            self._get_text(activity.find("siri:ValidUntilTime", self._siri_ns))
        )
        if valid_until is not None and self._to_utc(valid_until) < datetime.now(timezone.utc):
            return None

        recorded_at_time = self._parse_datetime(
            self._get_text(activity.find("siri:RecordedAtTime", self._siri_ns))
        )
        if recorded_at_time is not None and self._to_utc(recorded_at_time) < datetime.now(timezone.utc) - timedelta(minutes=5):
            return None

        monitored_journey = activity.find("siri:MonitoredVehicleJourney", self._siri_ns)
        if monitored_journey is None:
            logger.warning(
                "[SiriVmVehiclePositionsTransformer] Skipping vehicle activity: missing MonitoredVehicleJourney"
            )

            return None

        monitored = self._parse_bool(
            self._get_text(monitored_journey.find("siri:Monitored", self._siri_ns)),
            default=True,
        )

        if not monitored:
            return None

        if not self._matches_operator_filter(monitored_journey):
            return None

        vehicle_status = self._get_text(
            monitored_journey.find("siri:VehicleStatus", self._siri_ns)
        )

        if vehicle_status and vehicle_status.strip().lower() == "completed":
            return None

        trip_id = self._get_text(
            monitored_journey.find(
                "siri:FramedVehicleJourneyRef/siri:DatedVehicleJourneyRef",
                self._siri_ns,
            )
        )

        start_date = self._get_text(
            monitored_journey.find(
                "siri:FramedVehicleJourneyRef/siri:DataFrameRef",
                self._siri_ns,
            )
        )

        if not trip_id:
            logger.warning(
                "[SiriVmVehiclePositionsTransformer] Skipping vehicle activity due to missing DatedVehicleJourneyRef"
            )

            return None

        route_id = self._get_text(monitored_journey.find("siri:LineRef", self._siri_ns))
        if not route_id:
            logger.warning(
                "[SiriVmVehiclePositionsTransformer] Skipping vehicle activity %s due to missing LineRef",
                trip_id,
            )

            return None

        vehicle_ref = self._get_text(monitored_journey.find("siri:VehicleRef", self._siri_ns))
        if not vehicle_ref:
            logger.warning(
                "[SiriVmVehiclePositionsTransformer] Skipping vehicle activity %s due to missing VehicleRef",
                trip_id,
            )

            return None

        longitude_text = self._get_text(
            monitored_journey.find("siri:VehicleLocation/siri:Longitude", self._siri_ns)
        )

        latitude_text = self._get_text(
            monitored_journey.find("siri:VehicleLocation/siri:Latitude", self._siri_ns)
        )

        if not longitude_text or not latitude_text:
            logger.warning(
                "[SiriVmVehiclePositionsTransformer] Skipping vehicle activity %s due to missing longitude/latitude",
                trip_id,
            )

            return None

        try:
            longitude = float(longitude_text)
            latitude = float(latitude_text)
        except ValueError:
            logger.warning(
                "[SiriVmVehiclePositionsTransformer] Skipping vehicle activity %s due to invalid longitude/latitude",
                trip_id,
            )

            return None

        monitored_call = monitored_journey.find("siri:MonitoredCall", self._siri_ns)
        stop_id = None
        vehicle_at_stop = False
        current_stop_sequence = None

        if monitored_call is not None:
            stop_id = self._get_text(monitored_call.find("siri:StopPointRef", self._siri_ns))
            vehicle_at_stop = self._parse_bool(
                self._get_text(monitored_call.find("siri:VehicleAtStop", self._siri_ns)),
                default=False,
            )

            order_text = self._get_text(monitored_call.find("siri:Order", self._siri_ns))
            if order_text is not None:
                try:
                    current_stop_sequence = int(order_text)
                except ValueError:
                    logger.warning(
                        "[SiriVmVehiclePositionsTransformer] Ignoring non-integer MonitoredCall.Order '%s' for trip %s",
                        order_text,
                        trip_id,
                    )

        current_status = (
            VehicleStopStatus.STOPPED_AT.value
            if vehicle_at_stop
            else VehicleStopStatus.IN_TRANSIT_TO.value
        )

        is_complete_stop_sequence = self._parse_bool(
            self._get_text(monitored_journey.find("siri:IsCompleteStopSequence", self._siri_ns)),
            default=False,
        )

        call_candidates = self._collect_call_candidates(monitored_journey)
        call_time_tuples = self._extract_call_stop_time_tuples(call_candidates)
        if is_complete_stop_sequence and not call_time_tuples:
            logger.warning(
                "[SiriVmVehiclePositionsTransformer] Skipping vehicle activity %s due to missing usable aimed times in complete stop sequence calls",
                trip_id,
            )
            
            return None

        scheduled_intermediate_stops: list[tuple[str, datetime]] = []

        scheduled_start_stop_id = self._get_text(
            monitored_journey.find("siri:OriginRef", self._siri_ns)
        )

        scheduled_end_stop_id = self._get_text(
            monitored_journey.find("siri:DestinationRef", self._siri_ns)
        )
        scheduled_start_time: datetime | None = None
        scheduled_end_time: datetime | None = None

        if is_complete_stop_sequence:
            first_stop_id, first_time = call_time_tuples[0]
            last_stop_id, last_time = call_time_tuples[-1]
            scheduled_start_stop_id = first_stop_id
            scheduled_start_time = first_time
            scheduled_end_stop_id = last_stop_id
            scheduled_end_time = last_time
        else:
            sample_size = min(3, len(call_time_tuples))
            scheduled_intermediate_stops = random.sample(call_time_tuples, sample_size)

        timestamp = recorded_at_time

        if timestamp is None:
            timestamp = valid_until or datetime.now(timezone.utc)

        return {
            "trip": {
                "trip_id": trip_id,
                "start_time": "",
                "start_date": start_date or "",
                "route_id": route_id,
                "schedule_relationship": "SCHEDULED",
                "assignment_type": "ASSIGNED",
                "is_active": True,
                "is_valid": True,
                "scheduled_start_stop_id": scheduled_start_stop_id,
                "scheduled_start_time": scheduled_start_time,
                "scheduled_end_stop_id": scheduled_end_stop_id,
                "scheduled_end_time": scheduled_end_time,
                "scheduled_intermediate_stops": scheduled_intermediate_stops,
            },
            "vehicle_id": vehicle_ref,
            "vehicle_label": vehicle_ref,
            "vehicle_wheelchair_accessible": WheelchairAccessible.UNKNOWN.value,
            "timestamp": timestamp,
            "latitude": latitude,
            "longitude": longitude,
            "current_stop_sequence": current_stop_sequence,
            "current_status": current_status,
            "congestion_level": CongestionLevel.UNKNOWN_CONGESTION_LEVEL.value,
            "stop_id": stop_id,
            "scheduled_start_stop_id": scheduled_start_stop_id,
            "scheduled_start_time": scheduled_start_time,
            "scheduled_end_stop_id": scheduled_end_stop_id,
            "scheduled_end_time": scheduled_end_time,
            "scheduled_intermediate_stops": scheduled_intermediate_stops,
        }

    def _collect_call_candidates(self, monitored_journey: ET.Element) -> list[ET.Element]:
        previous_calls = monitored_journey.findall("siri:PreviousCalls/siri:PreviousCall", self._siri_ns)
        onward_calls = monitored_journey.findall("siri:OnwardCalls/siri:OnwardCall", self._siri_ns)
        monitored_call = monitored_journey.find("siri:MonitoredCall", self._siri_ns)

        ordered_calls: list[ET.Element] = []
        ordered_calls.extend(previous_calls)

        if monitored_call is not None:
            ordered_calls.append(monitored_call)

        ordered_calls.extend(onward_calls)

        return ordered_calls

    def _extract_call_stop_time_tuples(self, calls: list[ET.Element]) -> list[tuple[str, datetime]]:
        extracted: list[tuple[str, datetime]] = []
        for call in calls:
            stop_id = self._get_text(call.find("siri:StopPointRef", self._siri_ns))

            aimed_departure = self._parse_datetime(
                self._get_text(call.find("siri:AimedDepartureTime", self._siri_ns))
            )

            aimed_arrival = self._parse_datetime(
                self._get_text(call.find("siri:AimedArrivalTime", self._siri_ns))
            )
            
            aimed_time = aimed_departure or aimed_arrival

            if stop_id and aimed_time is not None:
                extracted.append((stop_id, aimed_time))

        return extracted

    def _matches_operator_filter(self, monitored_journey: ET.Element) -> bool:
        if not self._filter_value:
            return True

        allowed_patterns = [
            pattern.strip()
            for pattern in self._filter_value.split(",")
            if pattern.strip()
        ]

        operator_ref = self._get_text(monitored_journey.find("siri:OperatorRef", self._siri_ns))
        if not operator_ref:
            return False

        return any(self._wildcard_matches(pattern, operator_ref) for pattern in allowed_patterns)

    @staticmethod
    def _wildcard_matches(pattern: str, value: str) -> bool:
        regex = re.escape(pattern).replace(r"\*", ".*")
        return bool(re.fullmatch(regex, value))

    @staticmethod
    def _get_text(element: ET.Element | None) -> str | None:
        if element is None or element.text is None:
            return None

        value = element.text.strip()
        return value or None

    @staticmethod
    def _parse_bool(value: str | None, *, default: bool) -> bool:
        if value is None:
            return default

        return value.strip().lower() == "true"

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None

        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(
                "[SiriVmVehiclePositionsTransformer] Failed to parse datetime value '%s'",
                value,
            )
            
            return None

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)