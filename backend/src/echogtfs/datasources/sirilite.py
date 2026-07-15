"""SIRI-Lite datasource for realtime data import."""

from __future__ import annotations

from enum import Enum
import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from echogtfs.datasources.base import DatasourceBase
from echogtfs.datasources.transformers import (
    SiriLiteSwissServiceAlertsTransformer,
    SiriSxServiceAlertsTransformer,
)

logger = logging.getLogger("uvicorn")


class SiriLiteDialect(str, Enum):
    SWISS = "swiss"
    SIRISX = "sirisx"


class SiriLiteDatasource(DatasourceBase):
    """Datasource implementation for SIRI-Lite feeds."""

    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "adapter.sirilite.endpoint.label",
            "required": True,
            "placeholder": "adapter.sirilite.endpoint.placeholder",
            "help_text": "adapter.sirilite.endpoint.help_text",
        },
        {
            "name": "token",
            "type": "password",
            "label": "adapter.sirilite.token.label",
            "required": False,
            "placeholder": "adapter.sirilite.token.placeholder",
            "help_text": "adapter.sirilite.token.help_text",
        },
        {
            "name": "dialect",
            "type": "enum",
            "label": "adapter.sirilite.dialect.label",
            "required": True,
            "options": ["swiss", "sirisx"],
            "help_text": "adapter.sirilite.dialect.help_text",
        },
        {
            "name": "filter",
            "type": "text",
            "label": "adapter.sirilite.filter.label",
            "required": False,
            "placeholder": "adapter.sirilite.filter.placeholder",
            "help_text": "adapter.sirilite.filter.help_text",
        },
    ]

    def _validate_config(self) -> None:
        if "endpoint" not in self.config:
            raise ValueError("SiriLite datasource requires 'endpoint' in config")

        if "dialect" not in self.config:
            raise ValueError("SiriLite datasource requires 'dialect' in config")

        if not isinstance(self.config["endpoint"], str):
            raise ValueError("'endpoint' must be a string")

        if "token" in self.config and self.config["token"] is not None:
            if not isinstance(self.config["token"], str):
                raise ValueError("'token' must be a string")

        try:
            SiriLiteDialect(self.config["dialect"])
        except ValueError:
            valid_dialects = [dialect.value for dialect in SiriLiteDialect]
            raise ValueError(f"'dialect' must be one of: {', '.join(valid_dialects)}")

        if "filter" in self.config and self.config["filter"]:
            if not isinstance(self.config["filter"], str):
                raise ValueError("'filter' must be a string")

    async def _fetch_records(self) -> dict[str, Any] | list[dict[str, Any]]:
        root = await self._fetch_and_parse_xml()
        source_name = self.config.get("_source_name", "sirilite")
        filter_value = self.config.get("filter", "")

        dialect = SiriLiteDialect(self.config["dialect"])
        if dialect == SiriLiteDialect.SWISS:
            transformer = SiriLiteSwissServiceAlertsTransformer(
                make_unique_id=self._make_unique_id,
                filter_value=filter_value,
            )
            records = transformer.transform({"root": root, "source_name": source_name})
            return {
                "record_type": "service_alerts",
                "records": records,
            }

        transformer = SiriSxServiceAlertsTransformer(
            make_unique_id=self._make_unique_id,
            filter_value=filter_value,
        )
        records = transformer.transform({"root": root, "source_name": source_name})
        return {
            "record_type": "service_alerts",
            "records": records,
        }

    async def _fetch_and_parse_xml(self) -> ET.Element:
        from echogtfs.services.database import get_repository
        from echogtfs.services.datalog import DatalogService

        endpoint = self.config["endpoint"]
        token = self.config.get("token", "").strip()

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        logger.info(f"[SiriLiteDatasource] Fetching SIRI-Lite feed from {endpoint}")

        response = None
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(endpoint, headers=headers)
                response.raise_for_status()
                xml_content = response.text
        except httpx.HTTPError as exc:
            logger.error(f"[SiriLiteDatasource] HTTP error fetching feed: {exc}")
            source_id = self.config.get("_source_id")
            if source_id and response is not None:
                try:
                    error_content = response.text if response.text else f"HTTP Error: {exc}"
                    await DatalogService(get_repository()).create_log_entry(
                        data_source_id=source_id,
                        request_url=str(response.url),
                        response_content=error_content,
                        request_headers=dict(headers) if headers else None,
                        response_headers=dict(response.headers) if response.headers else None,
                        response_mimetype="text/plain",
                        status_code=response.status_code if hasattr(response, "status_code") else None,
                    )
                except Exception as log_error:
                    logger.warning(
                        f"[SiriLiteDatasource] Failed to log error request: {log_error}"
                    )
            raise ValueError(f"Failed to fetch SIRI-Lite feed: {exc}")

        source_id = self.config.get("_source_id")
        if source_id:
            try:
                await DatalogService(get_repository()).create_log_entry(
                    data_source_id=source_id,
                    request_url=str(response.url),
                    response_content=xml_content,
                    request_headers=dict(headers) if headers else None,
                    response_headers=dict(response.headers),
                    response_mimetype="application/xml",
                    status_code=response.status_code,
                )
            except Exception as exc:
                logger.error(
                    f"[SiriLiteDatasource] Failed to log request: {exc}",
                    exc_info=True,
                )

        try:
            return ET.fromstring(xml_content)
        except ET.ParseError as exc:
            logger.error(f"[SiriLiteDatasource] Failed to parse XML: {exc}")
            raise ValueError(f"Failed to parse SIRI-Lite XML: {exc}")
