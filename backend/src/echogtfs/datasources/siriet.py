"""SIRI-ET datasource for trip-update data import."""

from __future__ import annotations

from enum import Enum
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

from echogtfs.datasources.base import DatasourceBase
from echogtfs.datasources.transformers import SiriEtTripUpdatesTransformer

logger = logging.getLogger("uvicorn")


class SiriEtMethod(str, Enum):
    REQUEST_RESPONSE = "request/response"
    PUBLISH_SUBSCRIBE = "publish/subscribe"


class SiriEtDialect(str, Enum):
    SIRIET = "siriet"


class SiriEtDatasource(DatasourceBase):
    """Datasource implementation for SIRI-ET feeds."""

    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "adapter.siriet.endpoint.label",
            "required": True,
            "placeholder": "adapter.siriet.endpoint.placeholder",
            "help_text": "adapter.siriet.endpoint.help_text",
        },
        {
            "name": "participantref",
            "type": "text",
            "label": "adapter.siriet.participantref.label",
            "required": True,
            "placeholder": "adapter.siriet.participantref.placeholder",
            "help_text": "adapter.siriet.participantref.help_text",
        },
        {
            "name": "method",
            "type": "enum",
            "label": "adapter.siriet.method.label",
            "required": True,
            "options": ["request/response", "publish/subscribe"],
            "help_text": "adapter.siriet.method.help_text",
        },
        {
            "name": "dialect",
            "type": "enum",
            "label": "adapter.siriet.dialect.label",
            "required": True,
            "options": ["siriet"],
            "help_text": "adapter.siriet.dialect.help_text",
        },
        {
            "name": "treat_unexpected_stop_as_added_stop",
            "type": "boolean",
            "label": "adapter.siriet.treat_unexpected_stop_as_added_stop.label",
            "required": True,
            "help_text": "adapter.siriet.treat_unexpected_stop_as_added_stop.help_text",
        },
        {
            "name": "treat_missing_stop_as_canceled_stop",
            "type": "boolean",
            "label": "adapter.siriet.treat_missing_stop_as_canceled_stop.label",
            "required": True,
            "help_text": "adapter.siriet.treat_missing_stop_as_canceled_stop.help_text",
        },
        {
            "name": "filter",
            "type": "text",
            "label": "adapter.siriet.filter.label",
            "required": False,
            "placeholder": "adapter.siriet.filter.placeholder",
            "help_text": "adapter.siriet.filter.help_text",
        },
    ]

    def _validate_config(self) -> None:
        self.config.setdefault("treat_unexpected_stop_as_added_stop", False)
        self.config.setdefault("treat_missing_stop_as_canceled_stop", False)

        if "endpoint" not in self.config:
            raise ValueError("SiriEt datasource requires 'endpoint' in config")

        if "participantref" not in self.config:
            raise ValueError("SiriEt datasource requires 'participantref' in config")

        if "method" not in self.config:
            raise ValueError("SiriEt datasource requires 'method' in config")

        if "dialect" not in self.config:
            raise ValueError("SiriEt datasource requires 'dialect' in config")

        if not isinstance(self.config["endpoint"], str):
            raise ValueError("'endpoint' must be a string")

        if not isinstance(self.config["participantref"], str):
            raise ValueError("'participantref' must be a string")

        try:
            SiriEtMethod(self.config["method"])
        except ValueError:
            valid_methods = [method.value for method in SiriEtMethod]
            raise ValueError(
                f"Invalid method '{self.config['method']}'. Valid options: {', '.join(valid_methods)}"
            )

        try:
            SiriEtDialect(self.config["dialect"])
        except ValueError:
            valid_dialects = [dialect.value for dialect in SiriEtDialect]
            raise ValueError(
                f"Invalid dialect '{self.config['dialect']}'. Valid options: {', '.join(valid_dialects)}"
            )

        for boolean_field in (
            "treat_unexpected_stop_as_added_stop",
            "treat_missing_stop_as_canceled_stop",
        ):
            if boolean_field in self.config and self.config[boolean_field] is not None:
                if not isinstance(self.config[boolean_field], bool):
                    raise ValueError(f"'{boolean_field}' must be a boolean")

        if "filter" in self.config and self.config["filter"]:
            if not isinstance(self.config["filter"], str):
                raise ValueError("'filter' must be a string")

    def _resolve_placeholders(self, url: str) -> str:
        return re.sub(
            r"\{participantRef\}",
            self.config.get("participantref", ""),
            url,
            flags=re.IGNORECASE,
        )

    def _build_request_xml(self) -> str:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        siri = ET.Element("Siri", attrib={"xmlns": "http://www.siri.org.uk/siri", "version": "2.0"})
        service_request = ET.SubElement(siri, "ServiceRequest")

        request_timestamp = ET.SubElement(service_request, "RequestTimestamp")
        request_timestamp.text = timestamp

        requestor_ref = ET.SubElement(service_request, "RequestorRef")
        requestor_ref.text = self.config.get("participantref", "")

        estimated_timetable = ET.SubElement(
            service_request,
            "EstimatedTimetableRequest",
            attrib={"version": "2.0"},
        )

        et_timestamp = ET.SubElement(estimated_timetable, "RequestTimestamp")
        et_timestamp.text = timestamp

        xml_string = ET.tostring(siri, encoding="unicode", method="xml")
        return f'<?xml version="1.0" encoding="UTF-8"?>{xml_string}'

    async def _fetch_records(self) -> dict[str, Any]:
        root = await self._fetch_and_parse_xml()
        source_name = self.config.get("_source_name", "siriet")
        self.config["treat_unexpected_stop_as_added_stop"] = bool(
            self.config.get("treat_unexpected_stop_as_added_stop", False)
        )
        self.config["treat_missing_stop_as_canceled_stop"] = bool(
            self.config.get("treat_missing_stop_as_canceled_stop", False)
        )

        dialect = SiriEtDialect(self.config["dialect"])
        if dialect == SiriEtDialect.SIRIET:
            transformer = SiriEtTripUpdatesTransformer(
                filter_value=self.config.get("filter", ""),
            )
        else:
            raise ValueError(f"Unknown SIRI-ET dialect: {dialect}")

        try:
            records = await self._run_cpu_bound(
                transformer.transform,
                {"root": root, "source_name": source_name},
            )
        except Exception as exc:
            logger.error(f"[SiriEtDatasource] Failed to transform payload: {exc}", exc_info=True)

            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=self.config.get("endpoint", ""),
                request_headers={"Content-Type": "application/xml; charset=utf-8"},
                response_headers=None,
                response_status_code=500,
                response_content=str(exc),
                response_content_type="text/plain",
            )

            raise ValueError(f"Failed to transform SIRI-ET payload: {exc}") from exc

        return {
            "record_type": "trip_updates",
            "records": records,
            "_transform_runtime_ms": transformer.get_runtime_duration_ms(),
        }

    async def _fetch_and_parse_xml(self) -> ET.Element:
        if self.config.get("method") == SiriEtMethod.PUBLISH_SUBSCRIBE.value:
            raise NotImplementedError(
                "Method 'publish/subscribe' is not yet supported. Please use 'request/response' instead."
            )

        endpoint_url = self._resolve_placeholders(self.config["endpoint"])
        xml_payload = self._build_request_xml()

        response = None
        request_headers = {"Content-Type": "application/xml; charset=utf-8"}
        try:
            logger.info(f"[SiriEtDatasource] Fetching SIRI-ET feed from {endpoint_url}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint_url,
                    content=xml_payload,
                    headers=request_headers,
                )

                response.raise_for_status()
                xml_content = response.text
        except httpx.HTTPError as exc:
            logger.error(f"[SiriEtDatasource] HTTP error fetching feed: {exc}")

            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=endpoint_url,
                request_headers=request_headers,
                response_headers=dict(response.headers) if response and response.headers else None,
                response_status_code=response.status_code if response is not None else 404,
                response_content=str(exc),
                response_content_type="text/plain",
            )

            raise ValueError(f"Failed to fetch SIRI-ET feed: {exc}") from exc

        await self._log_request(
            source_id=self.config.get("_source_id"),
            request_url=endpoint_url,
            request_headers=request_headers,
            response_headers=dict(response.headers) if response and response.headers else None,
            response_status_code=response.status_code if response is not None else 404,
            response_content=xml_content,
            response_content_type="application/xml",
        )

        try:
            return await self._run_cpu_bound(ET.fromstring, xml_content)
        except ET.ParseError as exc:
            logger.error(f"[SiriEtDatasource] Failed to parse XML: {exc}")

            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=endpoint_url,
                request_headers=request_headers,
                response_headers=dict(response.headers) if response and response.headers else None,
                response_status_code=500,
                response_content=str(exc),
                response_content_type="text/plain",
            )

            raise ValueError(f"Failed to parse SIRI-ET XML: {exc}") from exc
