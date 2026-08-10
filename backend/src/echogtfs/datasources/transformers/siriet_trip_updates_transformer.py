"""SIRI-ET transformer for trip-update payloads."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from echogtfs.common.config import settings
from echogtfs.datasources.transformers.intf_trip_updates_transformer import (
    TripUpdatesTransformerInterface,
)

logger = logging.getLogger("uvicorn")


class SiriEtTripUpdatesTransformer(TripUpdatesTransformerInterface):
    """Transforms SIRI-ET XML payloads into trip-update dictionaries."""

    def __init__(self, filter_value: str | None = None):
        self._filter_value = (filter_value or "").strip()
        self._siri_ns = {"siri": "http://www.siri.org.uk/siri"}
        self._target_timezone = self._resolve_timezone(self._configured_timezone_name())
        self._runtime_duration_ms = 0.0

    def transform(self, raw_data: Any) -> list[dict[str, Any]]:
        """Transform SIRI-ET XML root to internal trip-update dictionaries."""
        self._runtime_duration_ms = 0.0
        start_time = perf_counter()
        root = raw_data["root"]

        journeys = root.findall(".//siri:EstimatedVehicleJourney", self._siri_ns)
        if not journeys:
            self._runtime_duration_ms = (perf_counter() - start_time) * 1000
            return []

        trips: list[dict[str, Any]] = []
        filtered_unmonitored = 0
        filtered_by_operator = 0
        filtered_incomplete = 0
        filtered_window = 0
        filtered_invalid = 0

        try:
            for journey in journeys:
                try:
                    monitored = self._parse_bool(
                        self._get_text(journey.find("siri:Monitored", self._siri_ns)),
                        default=True,
                    )

                    if not monitored:
                        filtered_unmonitored += 1
                        continue

                    if not self._matches_operator_filter(journey):
                        filtered_by_operator += 1
                        continue

                    if not self._is_new_trip_valid(journey):
                        filtered_incomplete += 1
                        logger.warning(
                            "[SiriEtTripUpdatesTransformer] Discarding NEW trip because IsCompleteStopSequence is not true."
                        )

                        continue

                    trip = self._parse_estimated_vehicle_journey(journey)
                    if trip is None:
                        filtered_invalid += 1
                        continue

                    if not self._is_in_trip_window(trip):
                        filtered_window += 1
                        continue

                    trips.append(trip)
                except Exception as exc:
                    trip_ref = self._get_text(
                        journey.find("siri:FramedVehicleJourneyRef/siri:DatedVehicleJourneyRef", self._siri_ns)
                    ) or "unknown"

                    logger.error(
                        "[SiriEtTripUpdatesTransformer] Error parsing journey %s: %s",
                        trip_ref,
                        exc,
                    )

            logger.info(
                "[SiriEtTripUpdatesTransformer] Processed %s trip updates (filtered: %s unmonitored, %s operator, %s incomplete, %s window, %s invalid)",
                len(trips),
                filtered_unmonitored,
                filtered_by_operator,
                filtered_incomplete,
                filtered_window,
                filtered_invalid,
            )

            return trips
        finally:
            self._runtime_duration_ms = (perf_counter() - start_time) * 1000

    def get_runtime_duration_ms(self) -> float:
        return float(self._runtime_duration_ms)

    def _is_new_trip_valid(self, journey: ET.Element) -> bool:
        extra_journey = self._parse_bool(
            self._get_text(journey.find("siri:ExtraJourney", self._siri_ns)),
            default=False,
        )
        if not extra_journey:
            return True

        is_complete_stop_sequence = self._parse_bool(
            self._get_text(journey.find("siri:IsCompleteStopSequence", self._siri_ns)),
            default=False,
        )

        return is_complete_stop_sequence

    def _parse_estimated_vehicle_journey(self, journey: ET.Element) -> dict[str, Any] | None:
        route_id = self._get_text(journey.find("siri:LineRef", self._siri_ns))
        trip_id = self._get_text(
            journey.find("siri:FramedVehicleJourneyRef/siri:DatedVehicleJourneyRef", self._siri_ns)
        )

        start_date = self._get_text(
            journey.find("siri:FramedVehicleJourneyRef/siri:DataFrameRef", self._siri_ns)
        )

        if not route_id or not trip_id:
            logger.warning(
                "[SiriEtTripUpdatesTransformer] Skipping journey due to missing LineRef or DatedVehicleJourneyRef"
            )

            return None

        all_calls = self._collect_all_calls(journey)
        if not all_calls:
            logger.warning(
                "[SiriEtTripUpdatesTransformer] Skipping journey %s: no RecordedCall/EstimatedCall entries",
                trip_id,
            )

            return None

        first_call = all_calls[0]
        last_call = all_calls[-1]

        scheduled_start_stop_id = self._get_text(first_call.find("siri:StopPointRef", self._siri_ns))
        scheduled_end_stop_id = self._get_text(last_call.find("siri:StopPointRef", self._siri_ns))

        scheduled_start_time = self._parse_datetime(
            self._get_text(first_call.find("siri:AimedDepartureTime", self._siri_ns))
            or self._get_text(first_call.find("siri:AimedArrivalTime", self._siri_ns))
        )

        scheduled_end_time = self._parse_datetime(
            self._get_text(last_call.find("siri:AimedArrivalTime", self._siri_ns))
            or self._get_text(last_call.find("siri:AimedDepartureTime", self._siri_ns))
        )

        if not scheduled_start_stop_id or not scheduled_end_stop_id:
            logger.warning(
                "[SiriEtTripUpdatesTransformer] Skipping journey %s: missing start/end StopPointRef",
                trip_id,
            )

            return None

        stop_events = self._extract_stop_events_from_calls(journey)
        if not stop_events:
            logger.warning(
                "[SiriEtTripUpdatesTransformer] Skipping journey %s: no stop events available",
                trip_id,
            )

            return None

        if not start_date and scheduled_start_time is not None:
            start_date = scheduled_start_time.date().isoformat()

        start_time = self._format_start_time(
            start_date=start_date,
            scheduled_start_time=scheduled_start_time,
        )

        trip_canceled = self._parse_bool(
            self._get_text(journey.find("siri:Cancellation", self._siri_ns)),
            default=False,
        )

        trip_extra_journey = self._parse_bool(
            self._get_text(journey.find("siri:ExtraJourney", self._siri_ns)),
            default=False,
        )

        schedule_relationship = "SCHEDULED"
        if trip_extra_journey:
            schedule_relationship = "NEW"
        elif trip_canceled:
            schedule_relationship = "CANCELED"

        return {
            "trip_id": trip_id,
            "route_id": route_id,
            "start_time": start_time,
            "start_date": start_date or "",
            "schedule_relationship": schedule_relationship,
            "is_complete_stop_sequence": True,
            "scheduled_start_stop_id": scheduled_start_stop_id,
            "scheduled_end_stop_id": scheduled_end_stop_id,
            "scheduled_start_time": scheduled_start_time,
            "scheduled_end_time": scheduled_end_time,
            "stop_events": stop_events,
        }

    def _extract_stop_events_from_calls(self, journey: ET.Element) -> list[dict[str, Any]]:
        stop_events: list[dict[str, Any]] = []

        recorded_calls = journey.findall("siri:RecordedCalls/siri:RecordedCall", self._siri_ns)
        for recorded_call in recorded_calls:
            stop_id = self._get_text(recorded_call.find("siri:StopPointRef", self._siri_ns))
            if not stop_id:
                continue

            actual_arrival_text = self._get_text(
                recorded_call.find("siri:ActualArrivalTime", self._siri_ns)
            )

            actual_departure_text = self._get_text(
                recorded_call.find("siri:ActualDepartureTime", self._siri_ns)
            )

            aimed_arrival_text = self._get_text(
                recorded_call.find("siri:AimedArrivalTime", self._siri_ns)
            )
            
            aimed_departure_text = self._get_text(
                recorded_call.find("siri:AimedDepartureTime", self._siri_ns)
            )

            has_realtime_data = bool(actual_arrival_text or actual_departure_text)

            arrival_time = self._parse_datetime(actual_arrival_text)
            departure_time = self._parse_datetime(actual_departure_text)

            if arrival_time is None:
                arrival_time = self._parse_datetime(aimed_arrival_text)

            if departure_time is None:
                departure_time = self._parse_datetime(aimed_departure_text)

            if arrival_time is None and departure_time is not None:
                arrival_time = departure_time

            if departure_time is None and arrival_time is not None:
                departure_time = arrival_time

            is_canceled = self._parse_bool(
                self._get_text(recorded_call.find("siri:Cancellation", self._siri_ns)),
                default=False,
            )

            schedule_relationship = "SCHEDULED"
            if is_canceled:
                schedule_relationship = "SKIPPED"
            elif not has_realtime_data:
                schedule_relationship = "NO_DATA"

            stop_events.append(
                {
                    "stop_id": stop_id,
                    "stop_sequence": self._get_text(recorded_call.find("siri:Order", self._siri_ns)),
                    "arrival_time": arrival_time,
                    "departure_time": departure_time,
                    "schedule_relationship": schedule_relationship,
                }
            )

        estimated_calls = journey.findall("siri:EstimatedCalls/siri:EstimatedCall", self._siri_ns)
        for estimated_call in estimated_calls:
            stop_id = self._get_text(estimated_call.find("siri:StopPointRef", self._siri_ns))
            if not stop_id:
                continue

            expected_arrival_text = self._get_text(
                estimated_call.find("siri:ExpectedArrivalTime", self._siri_ns)
            )

            expected_departure_text = self._get_text(
                estimated_call.find("siri:ExpectedDepartureTime", self._siri_ns)
            )

            aimed_arrival_text = self._get_text(
                estimated_call.find("siri:AimedArrivalTime", self._siri_ns)
            )

            aimed_departure_text = self._get_text(
                estimated_call.find("siri:AimedDepartureTime", self._siri_ns)
            )

            has_expected_data = bool(expected_arrival_text or expected_departure_text)

            arrival_time = self._parse_datetime(expected_arrival_text)
            departure_time = self._parse_datetime(expected_departure_text)

            if arrival_time is None:
                arrival_time = self._parse_datetime(aimed_arrival_text)

            if departure_time is None:
                departure_time = self._parse_datetime(aimed_departure_text)

            if arrival_time is None and departure_time is not None:
                arrival_time = departure_time

            if departure_time is None and arrival_time is not None:
                departure_time = arrival_time

            is_canceled = self._parse_bool(
                self._get_text(estimated_call.find("siri:Cancellation", self._siri_ns)),
                default=False,
            )

            is_extra_call = self._parse_bool(
                self._get_text(estimated_call.find("siri:ExtraCall", self._siri_ns)),
                default=False,
            )

            schedule_relationship = "SCHEDULED"
            if is_canceled:
                schedule_relationship = "SKIPPED"
            elif is_extra_call:
                schedule_relationship = "ADDED"
            elif not has_expected_data:
                schedule_relationship = "NO_DATA"

            stop_event = {
                "stop_id": stop_id,
                "stop_sequence": self._get_text(estimated_call.find("siri:Order", self._siri_ns)),
                "arrival_time": arrival_time,
                "departure_time": departure_time,
                "schedule_relationship": schedule_relationship,
            }

            stop_events.append(stop_event)

        return stop_events

    def _is_in_trip_window(self, trip: dict[str, Any]) -> bool:
        stop_events = trip.get("stop_events")
        if not isinstance(stop_events, list) or not stop_events:
            return False

        first_event = stop_events[0]
        first_timestamp = self._event_timestamp(first_event)
        if first_timestamp is None:
            return False

        now_utc = datetime.now(timezone.utc)
        if first_timestamp > now_utc + timedelta(hours=2):
            return False

        latest_timestamp: datetime | None = None
        for event in stop_events:
            event_ts = self._event_timestamp(event)
            if event_ts is None:
                continue

            if latest_timestamp is None or event_ts > latest_timestamp:
                latest_timestamp = event_ts

        if latest_timestamp is None:
            return False

        return latest_timestamp >= now_utc

    def _event_timestamp(self, stop_event: dict[str, Any]) -> datetime | None:
        arrival_time = self._to_utc(stop_event.get("arrival_time"))
        departure_time = self._to_utc(stop_event.get("departure_time"))

        if arrival_time is not None and departure_time is not None:
            return arrival_time if arrival_time <= departure_time else departure_time

        return arrival_time or departure_time

    def _to_utc(self, value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=self._target_timezone).astimezone(timezone.utc)

        return value.astimezone(timezone.utc)

    def _matches_operator_filter(self, journey: ET.Element) -> bool:
        if not self._filter_value:
            return True

        allowed_patterns = [
            operator.strip()
            for operator in self._filter_value.split(",")
            if operator.strip()
        ]

        operator_ref = self._get_text(journey.find("siri:OperatorRef", self._siri_ns))
        if not operator_ref:
            return False

        return any(self._wildcard_matches(pattern, operator_ref) for pattern in allowed_patterns)

    @staticmethod
    def _wildcard_matches(pattern: str, value: str) -> bool:
        regex = re.escape(pattern).replace(r"\*", ".*")
        return bool(re.fullmatch(regex, value))

    def _collect_all_calls(self, journey: ET.Element) -> list[ET.Element]:
        recorded_calls = journey.findall("siri:RecordedCalls/siri:RecordedCall", self._siri_ns)
        estimated_calls = journey.findall("siri:EstimatedCalls/siri:EstimatedCall", self._siri_ns)

        return [*recorded_calls, *estimated_calls]

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
                "[SiriEtTripUpdatesTransformer] Failed to parse datetime value '%s'",
                value,
            )
            
            return None

    @staticmethod
    def _configured_timezone_name() -> str:
        timezone_name = getattr(settings, "timezone", "UTC")
        if not isinstance(timezone_name, str) or not timezone_name.strip():
            return "UTC"

        return timezone_name

    @staticmethod
    def _resolve_timezone(timezone_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning(
                "[SiriEtTripUpdatesTransformer] Unknown TIMEZONE '%s'. Falling back to UTC",
                timezone_name,
            )
            
            return ZoneInfo("UTC")

    @staticmethod
    def _parse_service_date(value: str | None) -> date | None:
        if not value:
            return None

        candidate = value.strip()
        if not candidate:
            return None

        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue

        return None

    def _format_start_time(
        self,
        *,
        start_date: str | None,
        scheduled_start_time: datetime | None,
    ) -> str:
        if scheduled_start_time is None:
            return ""

        local_start_dt = scheduled_start_time
        if scheduled_start_time.tzinfo is not None:
            local_start_dt = scheduled_start_time.astimezone(self._target_timezone)

        service_date = self._parse_service_date(start_date)
        if service_date is None:
            return local_start_dt.strftime("%H:%M:%S")

        if local_start_dt.date() == service_date + timedelta(days=1):
            hours = local_start_dt.hour + 24
            return f"{hours:02d}:{local_start_dt.minute:02d}:{local_start_dt.second:02d}"

        return local_start_dt.strftime("%H:%M:%S")