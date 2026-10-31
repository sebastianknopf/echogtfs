"""VDV453 3.1 VIS transformer for vehicle-position payloads."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from echogtfs.common.config import settings
from echogtfs.enum.gtfsrt import CongestionLevel, VehicleStopStatus, WheelchairAccessible
from echogtfs.datasources.transformers.intf_vehicle_positions_transformer import (
    VehiclePositionsTransformerInterface,
)

logger = logging.getLogger("uvicorn")

_FRACTION_PATTERN = re.compile(r"\.(\d+)")
_INTEGER_PATTERN = re.compile(r"[+-]?\d+")

_MILLISECONDS_PER_DEGREE = 3_600_000
_MAX_RECORDED_AGE = timedelta(minutes=5)

_MELDUNGSART_POSITION = "Fahrplanlage"
_MELDUNGSARTEN_REMOVAL = frozenset({"Fahrtabbruch", "RegulaeresFahrtende", "BereichVerlassen"})


class Vdv453V31VehiclePositionsTransformer(VehiclePositionsTransformerInterface):
    """Transforms VDV453 3.1 VIS XML payloads into vehicle-position dictionaries."""

    def __init__(self, filters: dict[str, list[str]]):
        super().__init__(filters)
        self._runtime_duration_ms = 0.0
        self._target_timezone = self._resolve_timezone(self._configured_timezone_name())

    def transform(self, raw_data: Any) -> list[dict[str, Any]]:
        """Transform a VDV453 VIS XML root to internal vehicle-position dictionaries."""
        self._runtime_duration_ms = 0.0
        start_time = perf_counter()
        root = raw_data["root"]

        activities = root.findall(".//VISNachricht/VISFahrplanlage")
        if not activities:
            self._runtime_duration_ms = (perf_counter() - start_time) * 1000
            return []

        records: list[dict[str, Any]] = []
        filtered = 0

        try:
            for activity in activities:
                try:
                    meldungsart = self._child_text(activity, "VISMeldungsart")

                    if meldungsart == _MELDUNGSART_POSITION:
                        record = self._parse_vehicle_activity(activity)
                    elif meldungsart in _MELDUNGSARTEN_REMOVAL:
                        record = self._build_deletion_record(activity)
                    else:
                        logger.warning(
                            "[Vdv453V31VehiclePositionsTransformer] Skipping activity with unknown VISMeldungsart '%s'",
                            meldungsart,
                        )
                        record = None

                    if record is None:
                        filtered += 1
                        continue

                    records.append(record)
                except Exception as exc:
                    logger.error(
                        "[Vdv453V31VehiclePositionsTransformer] Error parsing activity %s: %s",
                        self._trip_id(activity) or "unknown",
                        exc,
                    )

            logger.info(
                "[Vdv453V31VehiclePositionsTransformer] Processed %s vehicle positions (filtered: %s)",
                len(records),
                filtered,
            )

            return records
        finally:
            self._runtime_duration_ms = (perf_counter() - start_time) * 1000

    def get_runtime_duration_ms(self) -> float:
        return float(self._runtime_duration_ms)

    # ------------------------------------------------------------------
    # Activity parsing
    # ------------------------------------------------------------------

    def _parse_vehicle_activity(self, activity: ET.Element) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)

        valid_until = self._parse_datetime(activity.get("VerfallZst"))
        if valid_until is not None and valid_until < now:
            return None

        recorded_at = self._parse_datetime(activity.get("Zst"))
        if recorded_at is not None and recorded_at < now - _MAX_RECORDED_AGE:
            return None

        if not self._matches_operator_filter(activity):
            return None

        if not self._matches_line_filter(activity):
            return None

        if not self._parse_bool(self._child_text(activity, "PrognoseMoeglich"), default=True):
            return self._build_deletion_record(activity)

        trip_id = self._trip_id(activity)
        route_id = self._child_text(activity, "LinienID")
        if not trip_id or not route_id:
            logger.warning(
                "[Vdv453V31VehiclePositionsTransformer] Skipping activity due to missing FahrtBezeichner or LinienID"
            )
            return None

        vehicle_id, vehicle_label = self._resolve_vehicle_identity(activity)
        if not vehicle_id:
            logger.warning(
                "[Vdv453V31VehiclePositionsTransformer] Skipping activity %s because no vehicle ID can be resolved",
                trip_id,
            )
            return None

        longitude_text = self._child_text(activity, "Longitude")
        latitude_text = self._child_text(activity, "Latitude")
        if not longitude_text or not latitude_text:
            logger.warning(
                "[Vdv453V31VehiclePositionsTransformer] Skipping activity %s due to missing longitude/latitude",
                trip_id,
            )
            return None

        longitude = self._parse_coordinate(longitude_text, 180)
        latitude = self._parse_coordinate(latitude_text, 90)
        if longitude is None or latitude is None:
            logger.warning(
                "[Vdv453V31VehiclePositionsTransformer] Skipping activity %s due to invalid longitude/latitude",
                trip_id,
            )
            return None

        stop_id, current_status = self._resolve_stop_status(activity)

        scheduled_start_time, scheduled_end_time, is_complete_stop_sequence = self._extract_schedule_times(activity)

        start_date = self._child_text(activity.find("FahrtID"), "Betriebstag")
        if not start_date and scheduled_start_time is not None:
            start_date = scheduled_start_time.astimezone(self._target_timezone).date().isoformat()

        timestamp = recorded_at or valid_until or now

        record: dict[str, Any] = {
            "trip": {
                "trip_id": trip_id,
                "start_time": self._format_start_time(
                    start_date=start_date,
                    scheduled_start_time=scheduled_start_time,
                ),
                "start_date": start_date or "",
                "route_id": route_id,
                "schedule_relationship": "SCHEDULED",
                "assignment_type": "ASSIGNED",
                "is_active": True,
                "is_complete_stop_sequence": is_complete_stop_sequence,
                "scheduled_start_stop_id": None,
                "scheduled_start_time": scheduled_start_time,
                "scheduled_end_stop_id": None,
                "scheduled_end_time": scheduled_end_time,
                "scheduled_intermediate_stops": [],
            },
            "is_deleted": False,
            "vehicle_id": vehicle_id,
            "vehicle_label": vehicle_label,
            "vehicle_wheelchair_accessible": WheelchairAccessible.UNKNOWN.value,
            "timestamp": timestamp,
            "latitude": latitude,
            "longitude": longitude,
            "current_status": current_status,
            "congestion_level": CongestionLevel.UNKNOWN_CONGESTION_LEVEL.value,
            "scheduled_start_stop_id": None,
            "scheduled_start_time": scheduled_start_time,
            "scheduled_end_stop_id": None,
            "scheduled_end_time": scheduled_end_time,
            "scheduled_intermediate_stops": [],
        }

        if stop_id:
            record["stop_id"] = stop_id

        return record

    def _build_deletion_record(self, activity: ET.Element) -> dict[str, Any] | None:
        """Build a deletion record; the vehicle ID and the trip reference identify the stored entity."""
        trip_id = self._trip_id(activity)
        vehicle_id, _ = self._resolve_vehicle_identity(activity)

        if not trip_id and not vehicle_id:
            return None

        record: dict[str, Any] = {"is_deleted": True}

        if vehicle_id:
            record["vehicle_id"] = vehicle_id

        if trip_id:
            record["trip"] = {"trip_id": trip_id}

        return record

    def _resolve_vehicle_identity(self, activity: ET.Element) -> tuple[str | None, str | None]:
        """Return (vehicle_id, vehicle_label), falling back to the journey reference without FahrzeugID."""
        vehicle_id = self._get_text(activity.find("FahrtInfo/FahrzeugID"))
        if vehicle_id:
            return vehicle_id, vehicle_id

        trip_id = self._trip_id(activity)
        service_date = self._child_text(activity.find("FahrtID"), "Betriebstag")
        if trip_id and service_date:
            return f"{service_date}|{trip_id}", None

        return None, None

    def _resolve_stop_status(self, activity: ET.Element) -> tuple[str | None, str]:
        at_stop = self._parse_bool(self._child_text(activity, "AufHst"), default=False)
        current_stop = self._get_text(activity.find("AktHaltID/HaltestellenID"))
        next_stop = self._get_text(activity.find("NachHaltID/HaltestellenID"))

        if at_stop and current_stop:
            return current_stop, VehicleStopStatus.STOPPED_AT.value

        return (None if at_stop else next_stop), VehicleStopStatus.IN_TRANSIT_TO.value

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
                "[Vdv453V31VehiclePositionsTransformer] Unknown TIMEZONE '%s'. Falling back to UTC",
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
        """Format the local start time; hours exceed 23 when the start lies on the day after the service date."""
        if scheduled_start_time is None:
            return ""

        local_start_dt = scheduled_start_time.astimezone(self._target_timezone)

        service_date = self._parse_service_date(start_date)
        if service_date is not None and local_start_dt.date() == service_date + timedelta(days=1):
            hours = local_start_dt.hour + 24
            return f"{hours:02d}:{local_start_dt.minute:02d}:{local_start_dt.second:02d}"

        return local_start_dt.strftime("%H:%M:%S")

    def _extract_schedule_times(
        self,
        activity: ET.Element,
    ) -> tuple[datetime | None, datetime | None, bool]:
        """Return (start_time, end_time, is_complete); times are only usable together with a start time."""
        start_time = self._parse_datetime(self._get_text(activity.find("FahrtInfo/AbfahrtszeitStartHst")))
        if start_time is None:
            return None, None, False

        end_time = self._parse_datetime(self._get_text(activity.find("FahrtInfo/AnkunftszeitZielHst")))

        return start_time, end_time, True

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def _matches_operator_filter(self, activity: ET.Element) -> bool:
        allowed_patterns = self._filters["legacy"] + self._filters["operator"]
        if not allowed_patterns:
            return True

        operator_id = self._get_text(activity.find("FahrtInfo/BetreiberID"))
        if not operator_id:
            return False

        return any(self.identifier_matches(operator_id, pattern) for pattern in allowed_patterns)

    def _matches_line_filter(self, activity: ET.Element) -> bool:
        allowed_patterns = self._filters["line"]
        if not allowed_patterns:
            return True

        line_id = self._child_text(activity, "LinienID")
        if not line_id:
            return False

        return any(self.identifier_matches(line_id, pattern) for pattern in allowed_patterns)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _trip_id(self, activity: ET.Element) -> str | None:
        return self._get_text(activity.find("FahrtID/FahrtBezeichner"))

    def _child_text(self, element: ET.Element | None, name: str) -> str | None:
        if element is None:
            return None

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

        return value.strip().lower() in ("true", "1")

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
                "[Vdv453V31VehiclePositionsTransformer] Failed to parse datetime value '%s'",
                value,
            )
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _parse_coordinate(value: str, limit: int) -> float | None:
        """Convert WGS-84 milliseconds of arc to degrees; return None for non-integers or out-of-range values."""
        candidate = value.strip()
        if not _INTEGER_PATTERN.fullmatch(candidate):
            return None

        degrees = int(candidate) / _MILLISECONDS_PER_DEGREE
        if abs(degrees) > limit:
            return None

        return degrees
