"""Transformer for EFA-JSON ADDINFO service-alert payloads."""

from __future__ import annotations

import ipaddress
import logging
import re
import time
from datetime import datetime
from html.parser import HTMLParser
from time import perf_counter
from typing import Any, Callable
from urllib.parse import urlsplit

from echogtfs.datasources.transformers.intf_service_alerts_transformer import (
    ServiceAlertsTransformerInterface,
)
from echogtfs.enum.gtfsrt import PeriodType

logger = logging.getLogger("uvicorn")


class _PlainTextHTMLParser(HTMLParser):
    """Extract plain text while preserving breaks between block elements."""

    _BLOCK_TAGS = {
        "br",
        "div",
        "li",
        "ol",
        "p",
        "section",
        "tr",
        "ul",
    }
    _IGNORED_TAGS = {"script", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        del _attrs
        if self._ignored_depth:
            if tag in self._IGNORED_TAGS:
                self._ignored_depth += 1
            return

        if tag in self._IGNORED_TAGS:
            self._ignored_depth = 1
        elif tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._ignored_depth:
            if tag in self._IGNORED_TAGS:
                self._ignored_depth -= 1
            return

        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


class EfaJsonServiceAlertsTransformer(ServiceAlertsTransformerInterface):
    """Transforms EFA-JSON ADDINFO entries into service-alert dictionaries."""

    SUPPORTED_LANGUAGES = ("DE", "EN")
    
    _PRIORITY_TO_SEVERITY = {
        "veryLow": "INFO",
        "low": "INFO",
        "high": "WARNING",
        "veryHigh": "SEVERE",
    }
    _ENTITYLESS_INFO_TYPES = {"generalInfo", "areaInfo"}
    _MAX_FUTURE_SECONDS = 30 * 24 * 60 * 60

    def __init__(
        self,
        make_unique_id: Callable[[str, str], Any],
        language: str,
        filters: dict[str, list[str]],
    ) -> None:
        super().__init__(filters)
        if language not in self.SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Invalid EFA-JSON language '{language}'. "
                f"Valid options: {', '.join(self.SUPPORTED_LANGUAGES)}"
            )

        self._make_unique_id = make_unique_id
        self._language = language
        self._runtime_duration_ms = 0.0

    def transform(self, raw_data: Any) -> list[dict[str, Any]]:
        """Transform the decoded EFA response into service-alert dictionaries."""
        self._runtime_duration_ms = 0.0
        start_time = perf_counter()

        try:
            if not isinstance(raw_data, dict):
                raise ValueError("EFA-JSON transformer input must be an object")

            response = raw_data.get("response")
            if not isinstance(response, dict):
                raise ValueError("EFA-JSON response must be a JSON object")

            source_name = raw_data.get("source_name")
            if not isinstance(source_name, str) or not source_name:
                source_name = "efa-json"

            if "infos" not in response:
                return []

            infos = response["infos"]
            if not isinstance(infos, dict):
                raise ValueError("EFA-JSON response 'infos' must be an object")
            if "current" not in infos:
                return []

            current_infos = infos["current"]
            if not isinstance(current_infos, list):
                raise ValueError("EFA-JSON response 'infos.current' must be a list")

            current_timestamp = int(time.time())
            alerts: list[dict[str, Any]] = []
            filtered = 0

            for info_index, info in enumerate(current_infos, start=1):
                if not isinstance(info, dict):
                    logger.warning(
                        "[EfaJsonServiceAlertsTransformer] Skipping non-object info at index %s",
                        info_index,
                    )
                    filtered += 1
                    continue

                alert = self._transform_info(info, source_name, current_timestamp)
                if alert is None:
                    filtered += 1
                    continue
                alerts.append(alert)

            logger.info(
                "[EfaJsonServiceAlertsTransformer] Processed %s alerts (filtered: %s)",
                len(alerts),
                filtered,
            )
            return alerts
        finally:
            self._runtime_duration_ms = (perf_counter() - start_time) * 1000

    def get_runtime_duration_ms(self) -> float:
        return float(self._runtime_duration_ms)

    _INFO_TYPE_ALIASES = {
        "lineBlocking": "lineInfo",
        "routeBlocking": "routeInfo",
        "stopBlocking": "stopInfo",
    }

    def _transform_info(
        self,
        info: dict[str, Any],
        source_name: str,
        current_timestamp: int,
    ) -> dict[str, Any] | None:
        info_type = info.get("type")
        if not isinstance(info_type, str):
            return None

        info_type = self._INFO_TYPE_ALIASES.get(info_type, info_type)
        if info_type not in {"lineInfo", "routeInfo", "stopInfo"} | self._ENTITYLESS_INFO_TYPES:
            return None

        if not self._matches_operator_filter(info):
            return None

        if info_type in self._ENTITYLESS_INFO_TYPES:
            informed_entities = []
        else:
            informed_entities = self._extract_informed_entities(
                info_type, info.get("affected")
            )
            if not informed_entities:
                return None
        if not self._matches_route_stop_filter(informed_entities):
            return None

        upstream_id = self._get_upstream_id(info)
        if upstream_id is None:
            return None
        alert_id = str(self._make_unique_id(upstream_id, source_name))

        translations = self._extract_translations(info.get("infoLinks"))
        if not translations:
            return None

        active_periods, windows, has_windows = self._extract_active_periods(info.get("timestamps"))
        if has_windows and not any(
            self._window_is_eligible(window, current_timestamp) for window in windows
        ):
            return None

        priority = info.get("priority")
        return {
            "id": alert_id,
            "is_deleted": False,
            "cause": "UNKNOWN_CAUSE",
            "effect": "UNKNOWN_EFFECT",
            "severity_level": self._PRIORITY_TO_SEVERITY.get(
                priority, "UNKNOWN_SEVERITY"
            ),
            "is_active": True,
            "translations": translations,
            "active_periods": active_periods,
            "informed_entities": informed_entities,
        }

    def _matches_operator_filter(self, info: dict[str, Any]) -> bool:
        allowed_patterns = self._filters["legacy"] + self._filters["operator"]
        if not allowed_patterns:
            return True

        properties = info.get("properties")
        property_values = properties if isinstance(properties, dict) else {}
        values = []
        for field in ("providerCode", "producerRef"):
            for value in (property_values.get(field), info.get(field)):
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())

        return any(
            self.identifier_matches(value, pattern)
            for value in values
            for pattern in allowed_patterns
        )

    def _matches_route_stop_filter(
        self,
        informed_entities: list[dict[str, Any]],
    ) -> bool:
        allowed_patterns = self._filters["line"]
        if not allowed_patterns:
            return True

        identifiers = [
            entity[field]
            for entity in informed_entities
            for field in ("route_id", "stop_id")
            if entity[field] is not None
        ]
        
        return any(
            self.identifier_matches(identifier, pattern)
            for identifier in identifiers
            for pattern in allowed_patterns
        )

    @staticmethod
    def _get_upstream_id(info: dict[str, Any]) -> str | None:
        properties = info.get("properties")
        message_ref = properties.get("messageRef") if isinstance(properties, dict) else None
        if isinstance(message_ref, (str, int)) and not isinstance(message_ref, bool):
            message_ref = str(message_ref).strip()
            if message_ref:
                return message_ref

        fallback_id = info.get("id")
        if isinstance(fallback_id, (str, int)) and not isinstance(fallback_id, bool):
            fallback_id = str(fallback_id).strip()
            if fallback_id:
                return fallback_id
        
        return None

    @classmethod
    def _extract_informed_entities(
        cls,
        info_type: str,
        affected: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(affected, dict):
            return []

        route_ids = cls._extract_ids(affected.get("lines"))
        stop_ids = cls._extract_ids(affected.get("stops"))

        if info_type == "lineInfo":
            return [
                cls._make_informed_entity(route_id=route_id)
                for route_id in route_ids
                if route_id is not None
            ]

        # stopInfo and routeInfo: one entity per stop and route combination
        route_ids = [route_id for route_id in route_ids if route_id is not None]
        stop_ids = [stop_id for stop_id in stop_ids if stop_id is not None]

        if stop_ids and route_ids:
            return [
                cls._make_informed_entity(route_id=route_id, stop_id=stop_id)
                for stop_id in stop_ids
                for route_id in route_ids
            ]

        if stop_ids:
            return [cls._make_informed_entity(stop_id=stop_id) for stop_id in stop_ids]

        return [cls._make_informed_entity(route_id=route_id) for route_id in route_ids]

    @staticmethod
    def _extract_ids(entries: Any) -> list[str | None]:
        if not isinstance(entries, list):
            return []

        identifiers: list[str | None] = []
        for entry in entries:
            value = entry.get("id") if isinstance(entry, dict) else None
            if isinstance(value, str):
                value = value.strip()
                identifiers.append(value or None)
            elif isinstance(value, int) and not isinstance(value, bool):
                identifiers.append(str(value))
            else:
                identifiers.append(None)
        
        return identifiers

    @staticmethod
    def _make_informed_entity(
        route_id: str | None = None,
        stop_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "agency_id": None,
            "route_id": route_id,
            "route_type": None,
            "stop_id": stop_id,
            "trip_id": None,
            "direction_id": None,
            "is_agency_valid": True,
            "is_route_valid": True,
            "is_stop_valid": True,
            "is_trip_valid": True,
        }

    def _extract_translations(self, info_links: Any) -> list[dict[str, Any]]:
        if not isinstance(info_links, list):
            return []

        translations = []
        for info_link in info_links:
            if not isinstance(info_link, dict):
                continue

            header_text = self._normalize_text(info_link.get("subtitle"))
            description_text = self._normalize_text(info_link.get("content"))
            if not header_text and not description_text:
                continue

            translations.append(
                {
                    "language": self._language,
                    "header_text": header_text or None,
                    "description_text": description_text or None,
                    "url": self._validated_url(info_link.get("url")),
                }
            )
        
        return translations

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if not isinstance(value, str) or not value:
            return ""

        parser = _PlainTextHTMLParser()
        parser.feed(value)
        parser.close()

        lines = []
        for line in "".join(parser.parts).splitlines():
            normalized_line = re.sub(r"\s+", " ", line).strip()
            if normalized_line:
                lines.append(normalized_line)
        
        return "\n".join(lines)

    @classmethod
    def _validated_url(cls, value: Any) -> str | None:
        if not isinstance(value, str):
            return None

        url = value.strip()
        if (
            not url
            or "\\" in url
            or re.search(r"%(?![0-9a-fA-F]{2})", url)
            or any(
                character.isspace() or ord(character) < 32 or ord(character) == 127
                for character in url
            )
        ):
            return None

        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError:
            return None

        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not hostname:
            return None

        authority = parsed.netloc.rsplit("@", 1)[-1]
        if authority.endswith(":"):
            return None
        if port is not None and not 1 <= port <= 65535:
            return None
        if not cls._is_valid_hostname(hostname):
            return None
        
        return url

    @staticmethod
    def _is_valid_hostname(hostname: str) -> bool:
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            pass

        try:
            ascii_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError:
            return False

        if ascii_hostname.endswith("."):
            ascii_hostname = ascii_hostname[:-1]
        if not ascii_hostname or len(ascii_hostname) > 253:
            return False

        labels = ascii_hostname.split(".")
        # A DNS name needs a domain part; single-label hosts such as "nohost" are rejected
        if len(labels) < 2:
            return False
        
        return all(
            label
            and len(label) <= 63
            and re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?", label)
            for label in labels
        )

    def _extract_active_periods(
        self,
        timestamps: Any,
    ) -> tuple[list[dict[str, Any]], list[tuple[int | None, int | None, bool]], bool]:
        if timestamps is None:
            return [], [], False
        if not isinstance(timestamps, dict):
            logger.warning(
                "[EfaJsonServiceAlertsTransformer] Invalid timestamps object"
            )
            
            return [], [], True

        active_periods = []
        windows: list[tuple[int | None, int | None, bool]] = []
        has_windows = False

        validity = timestamps.get("validity")
        if validity is not None:
            if not isinstance(validity, list):
                logger.warning(
                    "[EfaJsonServiceAlertsTransformer] Invalid timestamps.validity list"
                )
                has_windows = True
            else:
                for period in validity:
                    has_windows = True
                    if not isinstance(period, dict):
                        logger.warning(
                            "[EfaJsonServiceAlertsTransformer] Skipping invalid validity period"
                        )
                        continue
                    
                    active_period, window = self._parse_period(
                        period,
                        PeriodType.IMPACT_PERIOD,
                        "validity",
                    )
                    
                    active_periods.append(active_period)
                    windows.append(window)

        availability = timestamps.get("availability")
        if availability is not None:
            has_windows = True
            if not isinstance(availability, dict):
                logger.warning(
                    "[EfaJsonServiceAlertsTransformer] Invalid timestamps.availability object"
                )
            else:
                active_period, window = self._parse_period(
                    availability,
                    PeriodType.COMMUNICATION_PERIOD,
                    "availability",
                )
                
                active_periods.append(active_period)
                windows.append(window)

        return active_periods, windows, has_windows

    @classmethod
    def _parse_period(
        cls,
        raw_period: dict[str, Any],
        period_type: PeriodType,
        field_name: str,
    ) -> tuple[dict[str, Any], tuple[int | None, int | None, bool]]:
        start_time, start_failed = cls._parse_timestamp(
            raw_period.get("from"), f"{field_name}.from"
        )
        if raw_period.get("isOpenEnd") is True:
            end_time, end_failed = None, False
        else:
            end_time, end_failed = cls._parse_timestamp(raw_period.get("to"), f"{field_name}.to")

        if start_time is not None and end_time is not None and end_time < start_time:
            logger.warning(
                "[EfaJsonServiceAlertsTransformer] Invalid %s period: end precedes start",
                field_name,
            )
            end_failed = True

        return (
            {
                "period_type": period_type,
                "start_time": start_time,
                "end_time": end_time,
            },
            (start_time, end_time, not start_failed and not end_failed),
        )

    @staticmethod
    def _parse_timestamp(value: Any, field_name: str) -> tuple[int | None, bool]:
        if value is None or value == "":
            return None, False
        if not isinstance(value, str):
            logger.warning(
                "[EfaJsonServiceAlertsTransformer] Invalid timestamp for %s",
                field_name,
            )
            
            return None, True

        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return int(parsed.timestamp()), False
        except (ValueError, OverflowError) as exc:
            logger.warning(
                "[EfaJsonServiceAlertsTransformer] Failed to parse timestamp for %s: %s",
                field_name,
                exc,
            )
            
            return None, True

    @classmethod
    def _window_is_eligible(
        cls,
        window: tuple[int | None, int | None, bool],
        current_timestamp: int,
    ) -> bool:
        start_time, end_time, is_parseable = window
        if not is_parseable or start_time is None:
            return False

        if start_time <= current_timestamp:
            return end_time is None or end_time >= current_timestamp

        return start_time <= current_timestamp + cls._MAX_FUTURE_SECONDS
