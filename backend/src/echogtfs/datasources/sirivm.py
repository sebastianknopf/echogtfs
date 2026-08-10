"""SIRI-VM datasource for vehicle-position data import."""

from __future__ import annotations

from enum import Enum
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

from echogtfs.datasources.base import DatasourceBase
from echogtfs.datasources.transformers import SiriVmVehiclePositionsTransformer

logger = logging.getLogger("uvicorn")


class SiriVmMethod(str, Enum):
    REQUEST_RESPONSE = "request/response"
    PUBLISH_SUBSCRIBE = "publish/subscribe"


class SiriVmDialect(str, Enum):
    SIRIVM = "sirivm"


class SiriVmDatasource(DatasourceBase):
    """Datasource implementation for SIRI-VM feeds."""

    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "adapter.sirivm.endpoint.label",
            "required": True,
            "placeholder": "adapter.sirivm.endpoint.placeholder",
            "help_text": "adapter.sirivm.endpoint.help_text",
        },
        {
            "name": "participantref",
            "type": "text",
            "label": "adapter.sirivm.participantref.label",
            "required": True,
            "placeholder": "adapter.sirivm.participantref.placeholder",
            "help_text": "adapter.sirivm.participantref.help_text",
        },
        {
            "name": "method",
            "type": "enum",
            "label": "adapter.sirivm.method.label",
            "required": True,
            "options": ["request/response", "publish/subscribe"],
            "help_text": "adapter.sirivm.method.help_text",
        },
        {
            "name": "dialect",
            "type": "enum",
            "label": "adapter.sirivm.dialect.label",
            "required": True,
            "options": ["sirivm"],
            "help_text": "adapter.sirivm.dialect.help_text",
        },
        {
            "name": "filter",
            "type": "text",
            "label": "adapter.sirivm.filter.label",
            "required": False,
            "placeholder": "adapter.sirivm.filter.placeholder",
            "help_text": "adapter.sirivm.filter.help_text",
        },
    ]

    def _validate_config(self) -> None:
        if "endpoint" not in self.config:
            raise ValueError("SiriVm datasource requires 'endpoint' in config")

        if "participantref" not in self.config:
            raise ValueError("SiriVm datasource requires 'participantref' in config")

        if "method" not in self.config:
            raise ValueError("SiriVm datasource requires 'method' in config")

        if "dialect" not in self.config:
            raise ValueError("SiriVm datasource requires 'dialect' in config")

        if not isinstance(self.config["endpoint"], str):
            raise ValueError("'endpoint' must be a string")

        if not isinstance(self.config["participantref"], str):
            raise ValueError("'participantref' must be a string")

        try:
            SiriVmMethod(self.config["method"])
        except ValueError:
            valid_methods = [method.value for method in SiriVmMethod]
            raise ValueError(
                f"Invalid method '{self.config['method']}'. Valid options: {', '.join(valid_methods)}"
            )

        try:
            SiriVmDialect(self.config["dialect"])
        except ValueError:
            valid_dialects = [dialect.value for dialect in SiriVmDialect]
            raise ValueError(
                f"Invalid dialect '{self.config['dialect']}'. Valid options: {', '.join(valid_dialects)}"
            )

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

        vehicle_monitoring = ET.SubElement(
            service_request,
            "VehicleMonitoringRequest",
            attrib={"version": "2.0"},
        )

        vm_timestamp = ET.SubElement(vehicle_monitoring, "RequestTimestamp")
        vm_timestamp.text = timestamp

        # Highest-detail level for VM responses (includes call details).
        vm_detail_level = ET.SubElement(vehicle_monitoring, "VehicleMonitoringDetailLevel")
        vm_detail_level.text = "calls"

        include_situations = ET.SubElement(vehicle_monitoring, "IncludeSituations")
        include_situations.text = "false"

        include_translations = ET.SubElement(vehicle_monitoring, "IncludeTranslations")
        include_translations.text = "false"

        max_calls = ET.SubElement(vehicle_monitoring, "MaximumNumberOfCalls")
        max_calls_previous = ET.SubElement(max_calls, "Previous")
        max_calls_previous.text = "999"
        max_calls_onwards = ET.SubElement(max_calls, "Onwards")
        max_calls_onwards.text = "999"

        xml_string = ET.tostring(siri, encoding="unicode", method="xml")
        return f'<?xml version="1.0" encoding="UTF-8"?>{xml_string}'

    async def _fetch_records(self) -> dict[str, Any]:
        root = await self._fetch_and_parse_xml()
        source_name = self.config.get("_source_name", "sirivm")

        dialect = SiriVmDialect(self.config["dialect"])
        if dialect == SiriVmDialect.SIRIVM:
            transformer = SiriVmVehiclePositionsTransformer(
                filter_value=self.config.get("filter"),
            )
        else:
            raise ValueError(f"Unknown SIRI-VM dialect: {dialect}")

        try:
            records = await self._run_cpu_bound(
                transformer.transform,
                {"root": root, "source_name": source_name},
            )
        except Exception as exc:
            logger.error(f"[SiriVmDatasource] Failed to transform payload: {exc}", exc_info=True)

            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=self.config.get("endpoint", ""),
                request_headers={"Content-Type": "application/xml; charset=utf-8"},
                response_headers=None,
                response_status_code=500,
                response_content=str(exc),
                response_content_type="text/plain",
            )

            raise ValueError(f"Failed to transform SIRI-VM payload: {exc}") from exc

        return {
            "record_type": "vehicle_positions",
            "records": records,
            "_transform_runtime_ms": transformer.get_runtime_duration_ms(),
        }

    async def _fetch_and_parse_xml(self) -> ET.Element:
        if self.config.get("method") == SiriVmMethod.PUBLISH_SUBSCRIBE.value:
            raise NotImplementedError(
                "Method 'publish/subscribe' is not yet supported. Please use 'request/response' instead."
            )

        endpoint_url = self._resolve_placeholders(self.config["endpoint"])
        xml_payload = self._build_request_xml()

        response = None
        request_headers = {"Content-Type": "application/xml; charset=utf-8"}
        try:
            logger.info(f"[SiriVmDatasource] Fetching SIRI-VM feed from {endpoint_url}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint_url,
                    content=xml_payload,
                    headers=request_headers,
                )

                response.raise_for_status()
                xml_content = response.text
        except httpx.HTTPError as exc:
            logger.error(f"[SiriVmDatasource] HTTP error fetching feed: {exc}")

            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=endpoint_url,
                request_headers=request_headers,
                response_headers=dict(response.headers) if response and response.headers else None,
                response_status_code=response.status_code if response is not None else 404,
                response_content=str(exc),
                response_content_type="text/plain",
            )

            raise ValueError(f"Failed to fetch SIRI-VM feed: {exc}") from exc

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
            logger.error(f"[SiriVmDatasource] Failed to parse XML: {exc}")

            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=endpoint_url,
                request_headers=request_headers,
                response_headers=dict(response.headers) if response and response.headers else None,
                response_status_code=500,
                response_content=str(exc),
                response_content_type="text/plain",
            )

            raise ValueError(f"Failed to parse SIRI-VM XML: {exc}") from exc
