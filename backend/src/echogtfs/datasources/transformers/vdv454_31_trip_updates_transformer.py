"""VDV454 3.1 transformer for trip-update payloads."""

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

_FRACTION_PATTERN = re.compile(r"\.(\d+)")


class Vdv454V31TripUpdatesTransformer(TripUpdatesTransformerInterface):
    """Transforms VDV454 3.1 AUS XML payloads into trip-update dictionaries."""

    def __init__(self, filters: dict[str, list[str]]):
        super().__init__(filters)
        self._target_timezone = self._resolve_timezone(self._configured_timezone_name())
        self._runtime_duration_ms = 0.0

    def transform(self, raw_data: Any) -> list[dict[str, Any]]:
        """Transform a VDV454 AUS XML root to internal trip-update dictionaries."""
        self._runtime_duration_ms = 0.0
        start_time = perf_counter()
        root = raw_data["root"]

        journeys = root.findall(".//AUSNachricht/IstFahrt")
        if not journeys:
            self._runtime_duration_ms = (perf_counter() - start_time) * 1000
            return []

        trips: list[dict[str, Any]] = []
        filtered = 0

        try:
            for journey in journeys:
                try:
                    if not self._matches_operator_filter(journey):
                        filtered += 1
                        continue

                    if not self._matches_line_filter(journey):
                        filtered += 1
                        continue

                    if self._parse_bool(self._child_text(journey, "FahrtZuruecksetzen"), default=False):
                        trip_id = self._trip_id(journey)
                        if not trip_id:
                            filtered += 1
                            logger.warning(
                                "[Vdv454V31TripUpdatesTransformer] Skipping reset journey without FahrtBezeichner"
                            )
                            continue

                        trips.append({"trip_id": trip_id, "is_deleted": True})
                        continue

                    if not self._is_new_trip_valid(journey):
                        filtered += 1
                        logger.warning(
                            "[Vdv454V31TripUpdatesTransformer] Discarding NEW trip because Komplettfahrt is not true."
                        )
                        continue

                    trip = self._parse_ist_fahrt(journey)
                    if trip is None:
                        filtered += 1
                        continue

                    if not self._is_in_trip_window(trip):
                        filtered += 1
                        continue

                    trips.append(trip)
                except Exception as exc:
                    logger.error(
                        "[Vdv454V31TripUpdatesTransformer] Error parsing journey %s: %s",
                        self._trip_id(journey) or "unknown",
                        exc,
                    )

            logger.info(
                "[Vdv454V31TripUpdatesTransformer] Processed %s trip updates (filtered: %s)",
                len(trips),
                filtered,
            )

            return trips
        finally:
            self._runtime_duration_ms = (perf_counter() - start_time) * 1000

    def get_runtime_duration_ms(self) -> float:
        return float(self._runtime_duration_ms)

    # ------------------------------------------------------------------
    # Journey parsing
    # ------------------------------------------------------------------

    def _is_new_trip_valid(self, journey: ET.Element) -> bool:
        if not self._parse_bool(self._child_text(journey, "Zusatzfahrt"), default=False):
            return True

        return self._is_complete(journey)

    def _is_complete(self, journey: ET.Element) -> bool:
        return self._parse_bool(self._child_text(journey, "Komplettfahrt"), default=False)

    def _parse_ist_fahrt(self, journey: ET.Element) -> dict[str, Any] | None:
        route_id = self._child_text(journey, "LinienID")
        trip_id = self._trip_id(journey)

        if not route_id or not trip_id:
            logger.warning(
                "[Vdv454V31TripUpdatesTransformer] Skipping journey due to missing LinienID or FahrtBezeichner"
            )
            return None

        is_complete = self._is_complete(journey)
        is_canceled = self._parse_bool(self._child_text(journey, "FaelltAus"), default=False)
        is_extra_journey = self._parse_bool(self._child_text(journey, "Zusatzfahrt"), default=False)
        prediction_possible = self._parse_bool(
            self._child_text(journey, "PrognoseMoeglich"), default=True
        )

        halt_elements = journey.findall("IstHalt")
        stop_events = self._extract_stop_events(
            halt_elements,
            is_complete=is_complete,
            is_extra_journey=is_extra_journey,
            prediction_possible=prediction_possible,
        )

        if not stop_events and not is_canceled:
            logger.warning(
                "[Vdv454V31TripUpdatesTransformer] Skipping journey %s: no stop events available",
                trip_id,
            )
            return None

        anchors = self._resolve_anchors(journey, halt_elements, is_complete=is_complete)
        if anchors is None:
            logger.warning(
                "[Vdv454V31TripUpdatesTransformer] Skipping journey %s: missing start/end stop",
                trip_id,
            )
            return None

        start_stop_id, end_stop_id, start_time_value, end_time_value, anchor_start_time = anchors

        start_date = self._get_text(journey.find("FahrtRef/FahrtID/Betriebstag"))
        if not start_date and anchor_start_time is not None:
            start_date = anchor_start_time.astimezone(self._target_timezone).date().isoformat()

        start_time = None
        if is_complete:
            start_time = self._format_start_time(
                start_date=start_date,
                scheduled_start_time=anchor_start_time,
            )

        schedule_relationship = "SCHEDULED"
        if is_extra_journey:
            schedule_relationship = "NEW"
        elif is_canceled:
            schedule_relationship = "CANCELED"

        return {
            "trip_id": trip_id,
            "is_deleted": False,
            "route_id": route_id,
            "start_time": start_time,
            "start_date": start_date or "",
            "schedule_relationship": schedule_relationship,
            "is_complete_stop_sequence": is_complete,
            "scheduled_start_stop_id": start_stop_id,
            "scheduled_end_stop_id": end_stop_id,
            "scheduled_start_time": start_time_value,
            "scheduled_end_time": end_time_value,
            "scheduled_intermediate_stops": self._extract_scheduled_intermediate_stops(
                halt_elements, is_complete=is_complete
            ),
            "stop_events": stop_events,
        }

    def _resolve_anchors(
        self,
        journey: ET.Element,
        halt_elements: list[ET.Element],
        *,
        is_complete: bool,
    ) -> tuple[str, str, datetime | None, datetime | None, datetime | None] | None:
        """Return start stop, end stop, start time, end time and the start time used for start_time."""
        first_halt = halt_elements[0] if halt_elements else None
        last_halt = halt_elements[-1] if halt_elements else None

        fallback_start_time = None
        fallback_end_time = None
        if first_halt is not None:
            fallback_start_time = self._parse_datetime(
                self._child_text(first_halt, "Abfahrtszeit")
            ) or self._parse_datetime(self._child_text(first_halt, "Ankunftszeit"))
        if last_halt is not None:
            fallback_end_time = self._parse_datetime(
                self._child_text(last_halt, "Ankunftszeit")
            ) or self._parse_datetime(self._child_text(last_halt, "Abfahrtszeit"))

        start_end = journey.find("FahrtRef/FahrtStartEnde")
        if start_end is not None:
            start_stop_id = self._get_text(start_end.find("StartHaltID/HaltestellenID"))
            end_stop_id = self._get_text(start_end.find("EndHaltID/HaltestellenID"))
            start_time = self._parse_datetime(self._child_text(start_end, "Startzeit"))
            end_time = self._parse_datetime(self._child_text(start_end, "Endzeit"))

            if start_stop_id and end_stop_id:
                return (
                    start_stop_id,
                    end_stop_id,
                    start_time,
                    end_time,
                    start_time or (fallback_start_time if is_complete else None),
                )

        if first_halt is None or last_halt is None:
            return None

        start_stop_id = self._get_text(first_halt.find("HaltID/HaltestellenID"))
        end_stop_id = self._get_text(last_halt.find("HaltID/HaltestellenID"))
        if not start_stop_id or not end_stop_id:
            return None

        start_time = fallback_start_time if is_complete else None
        end_time = fallback_end_time if is_complete else None

        return start_stop_id, end_stop_id, start_time, end_time, start_time

    def _extract_scheduled_intermediate_stops(
        self,
        halt_elements: list[ET.Element],
        *,
        is_complete: bool,
    ) -> list[tuple[str, datetime]]:
        if is_complete:
            if len(halt_elements) <= 2:
                return []
            candidates = halt_elements[1:-1]
        else:
            candidates = halt_elements

        extracted: list[tuple[str, datetime]] = []
        for halt in candidates:
            stop_id = self._get_text(halt.find("HaltID/HaltestellenID"))
            if not stop_id:
                continue

            scheduled_time = self._parse_datetime(
                self._child_text(halt, "Abfahrtszeit")
            ) or self._parse_datetime(self._child_text(halt, "Ankunftszeit"))
            if scheduled_time is None:
                continue

            extracted.append((stop_id, scheduled_time))

        return extracted

    def _extract_stop_events(
        self,
        halt_elements: list[ET.Element],
        *,
        is_complete: bool,
        is_extra_journey: bool,
        prediction_possible: bool,
    ) -> list[dict[str, Any]]:
        stop_events: list[dict[str, Any]] = []

        for index, halt in enumerate(halt_elements, start=1):
            stop_id = self._get_text(halt.find("HaltID/HaltestellenID"))
            if not stop_id:
                continue

            scheduled_arrival_time = self._parse_datetime(self._child_text(halt, "Ankunftszeit"))
            scheduled_departure_time = self._parse_datetime(self._child_text(halt, "Abfahrtszeit"))

            predicted_arrival_time = None
            predicted_departure_time = None
            if prediction_possible:
                predicted_arrival_time = self._parse_prediction(
                    halt, "IstAnkunftPrognose", "IstAnkunftPrognoseStatus"
                )
                predicted_departure_time = self._parse_prediction(
                    halt, "IstAbfahrtPrognose", "IstAbfahrtPrognoseStatus"
                )

            has_realtime_data = predicted_arrival_time is not None or predicted_departure_time is not None

            arrival_time = predicted_arrival_time or scheduled_arrival_time
            departure_time = predicted_departure_time or scheduled_departure_time

            if arrival_time is None and departure_time is not None:
                arrival_time = departure_time

            if departure_time is None and arrival_time is not None:
                departure_time = arrival_time

            is_pass_through = self._parse_bool(self._child_text(halt, "Durchfahrt"), default=False)
            is_extra_call = self._parse_bool(self._child_text(halt, "Zusatzhalt"), default=False)

            if is_pass_through:
                schedule_relationship = "SKIPPED"
            elif is_extra_call and not is_extra_journey:
                schedule_relationship = "ADDED"
            elif not has_realtime_data:
                schedule_relationship = "NO_DATA"
            else:
                schedule_relationship = "SCHEDULED"

            stop_events.append(
                {
                    "stop_id": stop_id,
                    "stop_sequence": str(index) if is_complete else "",
                    "arrival_time": arrival_time,
                    "departure_time": departure_time,
                    "scheduled_arrival_time": scheduled_arrival_time,
                    "scheduled_departure_time": scheduled_departure_time,
                    "schedule_relationship": schedule_relationship,
                }
            )

        return stop_events

    def _parse_prediction(
        self,
        halt: ET.Element,
        value_name: str,
        status_name: str,
    ) -> datetime | None:
        status = self._child_text(halt, status_name)
        if status is not None and status.strip().lower() == "unbekannt":
            return None

        return self._parse_datetime(self._child_text(halt, value_name))

    def _trip_id(self, journey: ET.Element) -> str | None:
        return self._get_text(journey.find("FahrtRef/FahrtID/FahrtBezeichner"))

    # ------------------------------------------------------------------
    # Trip window
    # ------------------------------------------------------------------

    def _is_in_trip_window(self, trip: dict[str, Any]) -> bool:
        stop_events = trip.get("stop_events")
        if not isinstance(stop_events, list):
            return False

        if stop_events:
            first_timestamp = self._event_timestamp(stop_events[0])
            event_timestamps = [
                ts for ts in (self._event_timestamp(event) for event in stop_events) if ts is not None
            ]
            latest_timestamp = max(event_timestamps) if event_timestamps else None
        else:
            # Cancelled journey without stops: fall back to the scheduled start/end anchors.
            first_timestamp = self._to_utc(trip.get("scheduled_start_time"))
            latest_timestamp = self._to_utc(trip.get("scheduled_end_time"))

        if first_timestamp is None:
            return False

        now_utc = datetime.now(timezone.utc)
        if first_timestamp > now_utc + timedelta(hours=2):
            return False

        if not trip.get("is_complete_stop_sequence", True):
            return True

        if latest_timestamp is None:
            return False

        return latest_timestamp >= now_utc

    def _event_timestamp(self, stop_event: dict[str, Any]) -> datetime | None:
        arrival_time = self._to_utc(stop_event.get("arrival_time"))
        departure_time = self._to_utc(stop_event.get("departure_time"))

        if arrival_time is not None and departure_time is not None:
            return min(arrival_time, departure_time)

        return arrival_time or departure_time

    @staticmethod
    def _to_utc(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def _matches_operator_filter(self, journey: ET.Element) -> bool:
        allowed_patterns = self._filters["legacy"] + self._filters["operator"]
        if not allowed_patterns:
            return True

        operator_id = self._child_text(journey, "BetreiberID")
        if not operator_id:
            return False

        return any(self.identifier_matches(operator_id, pattern) for pattern in allowed_patterns)

    def _matches_line_filter(self, journey: ET.Element) -> bool:
        allowed_patterns = self._filters["line"]
        if not allowed_patterns:
            return True

        line_id = self._child_text(journey, "LinienID")
        if not line_id:
            return False

        return any(self.identifier_matches(line_id, pattern) for pattern in allowed_patterns)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _child_text(self, element: ET.Element, name: str) -> str | None:
        return self._get_text(element.find(name))

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
        """Parse an ISO 8601 timestamp; values without offset are interpreted as UTC."""
        if not value:
            return None

        candidate = value.strip().replace("Z", "+00:00")
        # datetime.fromisoformat on Python 3.10 only accepts 3 or 6 fractional digits.
        candidate = _FRACTION_PATTERN.sub(
            lambda match: "." + match.group(1)[:6].ljust(6, "0"), candidate, count=1
        )

        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            logger.warning(
                "[Vdv454V31TripUpdatesTransformer] Failed to parse datetime value '%s'",
                value,
            )
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

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
                "[Vdv454V31TripUpdatesTransformer] Unknown TIMEZONE '%s'. Falling back to UTC",
                timezone_name,
            )

            return ZoneInfo("UTC")

    @staticmethod
    def _parse_service_date(value: str | None) -> date | None:
        if not value:
            return None

        candidate = value.strip()
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

        local_start_dt = scheduled_start_time.astimezone(self._target_timezone)

        service_date = self._parse_service_date(start_date)
        if service_date is not None and local_start_dt.date() == service_date + timedelta(days=1):
            hours = local_start_dt.hour + 24
            return f"{hours:02d}:{local_start_dt.minute:02d}:{local_start_dt.second:02d}"

        return local_start_dt.strftime("%H:%M:%S")
