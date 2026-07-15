"""SIRI-SX datasource for realtime data import."""

from __future__ import annotations

from enum import Enum
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

from echogtfs.datasources.base import DatasourceBase
from echogtfs.datasources.transformers import SiriSxServiceAlertsTransformer

logger = logging.getLogger("uvicorn")


class SiriSxMethod(str, Enum):
    REQUEST_RESPONSE = "request/response"
    PUBLISH_SUBSCRIBE = "publish/subscribe"


class SiriSxDialect(str, Enum):
    SIRISX = "sirisx"


class SiriSxDatasource(DatasourceBase):
    """Datasource implementation for SIRI-SX feeds."""

    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "adapter.sirisx.endpoint.label",
            "required": True,
            "placeholder": "adapter.sirisx.endpoint.placeholder",
            "help_text": "adapter.sirisx.endpoint.help_text",
        },
        {
            "name": "participantref",
            "type": "text",
            "label": "adapter.sirisx.participantref.label",
            "required": True,
            "placeholder": "adapter.sirisx.participantref.placeholder",
            "help_text": "adapter.sirisx.participantref.help_text",
        },
        {
            "name": "method",
            "type": "enum",
            "label": "adapter.sirisx.method.label",
            "required": True,
            "options": ["request/response", "publish/subscribe"],
            "help_text": "adapter.sirisx.method.help_text",
        },
        {
            "name": "dialect",
            "type": "enum",
            "label": "adapter.sirisx.dialect.label",
            "required": True,
            "options": ["sirisx"],
            "help_text": "adapter.sirisx.dialect.help_text",
        },
        {
            "name": "filter",
            "type": "text",
            "label": "adapter.sirisx.filter.label",
            "required": False,
            "placeholder": "adapter.sirisx.filter.placeholder",
            "help_text": "adapter.sirisx.filter.help_text",
        },
    ]

    def _validate_config(self) -> None:
        if "endpoint" not in self.config:
            raise ValueError("SiriSx datasource requires 'endpoint' in config")

        if "participantref" not in self.config:
            raise ValueError("SiriSx datasource requires 'participantref' in config")

        if "method" not in self.config:
            raise ValueError("SiriSx datasource requires 'method' in config")

        if "dialect" not in self.config:
            raise ValueError("SiriSx datasource requires 'dialect' in config")

        if not isinstance(self.config["endpoint"], str):
            raise ValueError("'endpoint' must be a string")

        if not isinstance(self.config["participantref"], str):
            raise ValueError("'participantref' must be a string")

        try:
            SiriSxMethod(self.config["method"])
        except ValueError:
            valid_methods = [method.value for method in SiriSxMethod]
            raise ValueError(
                f"Invalid method '{self.config['method']}'. Valid options: {', '.join(valid_methods)}"
            )

        try:
            SiriSxDialect(self.config["dialect"])
        except ValueError:
            valid_dialects = [dialect.value for dialect in SiriSxDialect]
            raise ValueError(
                f"Invalid dialect '{self.config['dialect']}'. Valid options: {', '.join(valid_dialects)}"
            )

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

        situation_exchange = ET.SubElement(
            service_request,
            "SituationExchangeRequest",
            attrib={"version": "2.0"},
        )
        sx_timestamp = ET.SubElement(situation_exchange, "RequestTimestamp")
        sx_timestamp.text = timestamp

        xml_string = ET.tostring(siri, encoding="unicode", method="xml")
        return f'<?xml version="1.0" encoding="UTF-8"?>{xml_string}'

    async def _fetch_records(self) -> dict[str, Any] | list[dict[str, Any]]:
        from echogtfs.services.database import get_repository
        from echogtfs.services.datalog import DatalogService

        if self.config.get("method") == SiriSxMethod.PUBLISH_SUBSCRIBE.value:
            raise NotImplementedError(
                "Method 'publish/subscribe' is not yet supported. Please use 'request/response' instead."
            )

        endpoint_url = self._resolve_placeholders(self.config["endpoint"])
        xml_payload = self._build_request_xml()

        response = None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint_url,
                    content=xml_payload,
                    headers={"Content-Type": "application/xml; charset=utf-8"},
                )
                response.raise_for_status()
                xml_content = response.text
        except httpx.HTTPError as exc:
            logger.error(f"[SiriSxDatasource] HTTP error fetching feed: {exc}")
            source_id = self.config.get("_source_id")
            if source_id and response is not None:
                try:
                    error_content = response.text if response.text else f"HTTP Error: {exc}"
                    await DatalogService(get_repository()).create_log_entry(
                        data_source_id=source_id,
                        request_url=endpoint_url,
                        response_content=error_content,
                        request_headers={"Content-Type": "application/xml; charset=utf-8"},
                        response_headers=dict(response.headers) if response.headers else None,
                        response_mimetype="text/plain",
                        status_code=response.status_code if hasattr(response, "status_code") else None,
                    )
                except Exception as log_error:
                    logger.warning(
                        f"[SiriSxDatasource] Failed to log error request: {log_error}"
                    )
            raise ValueError(f"Failed to fetch SIRI-SX feed: {exc}")

        source_id = self.config.get("_source_id")
        if source_id:
            try:
                await DatalogService(get_repository()).create_log_entry(
                    data_source_id=source_id,
                    request_url=endpoint_url,
                    response_content=xml_content,
                    request_headers={"Content-Type": "application/xml; charset=utf-8"},
                    response_headers=dict(response.headers),
                    response_mimetype="application/xml",
                    status_code=response.status_code,
                )
            except Exception as exc:
                logger.error(f"[SiriSxDatasource] Failed to log request: {exc}", exc_info=True)

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as exc:
            logger.error(f"[SiriSxDatasource] Failed to parse XML: {exc}")
            raise ValueError(f"Failed to parse SIRI-SX XML: {exc}")

        transformer = SiriSxServiceAlertsTransformer(
            make_unique_id=self._make_unique_id,
            filter_value=self.config.get("filter", ""),
        )
        records = transformer.transform(
            {
                "root": root,
                "source_name": self.config.get("_source_name", "sirisx"),
            }
        )
        return {
            "record_type": "service_alerts",
            "records": records,
        }
