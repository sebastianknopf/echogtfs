"""EFA-JSON datasource for ADDINFO service-alert payloads."""

from __future__ import annotations

from enum import Enum
import json
import logging
from typing import Any

import httpx

from echogtfs.datasources.base import DatasourceBase
from echogtfs.datasources.intf_datasource import DatasourceCapabilities
from echogtfs.enum.system import DataSourceExecutionType
from echogtfs.datasources.transformers import EfaJsonServiceAlertsTransformer

logger = logging.getLogger("uvicorn")


class EfaJsonDialect(str, Enum):
    ADDINFO = "ADDINFO"


class EfaJsonDatasource(DatasourceBase):
    """Datasource implementation for EFA-JSON service-alert feeds."""

    # UserAgent for HTTP requests to EFA-JSON endpoints
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"

    CAPABILITIES = DatasourceCapabilities(
        execution_types=(DataSourceExecutionType.TIME_BASED, DataSourceExecutionType.EVENT_BASED),
        differential_updates=False,
    )

    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "adapter.efa-json.endpoint.label",
            "required": True,
            "placeholder": "adapter.efa-json.endpoint.placeholder",
            "help_text": "adapter.efa-json.endpoint.help_text",
        },
        {
            "name": "dialect",
            "type": "enum",
            "label": "adapter.efa-json.dialect.label",
            "required": True,
            "options": [dialect.value for dialect in EfaJsonDialect],
            "help_text": "adapter.efa-json.dialect.help_text",
        },
        {
            "name": "language",
            "type": "enum",
            "label": "adapter.efa-json.language.label",
            "required": True,
            "options": list(EfaJsonServiceAlertsTransformer.SUPPORTED_LANGUAGES),
            "help_text": "adapter.efa-json.language.help_text",
        },
        {
            "name": "filter",
            "type": "taglist",
            "label": "adapter.efa-json.filter.label",
            "required": False,
            "placeholder": "adapter.efa-json.filter.placeholder",
            "help_text": "adapter.efa-json.filter.help_text",
        },
    ]

    def get_datasource_type(self) -> str:
        return "efa-json"

    def _validate_config(self) -> None:
        endpoint = self.config.get("endpoint")
        if not endpoint:
            if not self._is_event_based_execution():
                raise ValueError("EFA-JSON datasource requires 'endpoint' in config")
        elif not isinstance(endpoint, str):
            raise ValueError("'endpoint' must be a string")

        if "dialect" not in self.config:
            raise ValueError("EFA-JSON datasource requires 'dialect' in config")

        try:
            EfaJsonDialect(self.config["dialect"])
        except (TypeError, ValueError):
            valid_dialects = [dialect.value for dialect in EfaJsonDialect]
            raise ValueError(
                f"Invalid EFA-JSON dialect '{self.config['dialect']}'. "
                f"Valid options: {', '.join(valid_dialects)}"
            )

        language = self.config.get("language")
        if language not in EfaJsonServiceAlertsTransformer.SUPPORTED_LANGUAGES:
            raise ValueError(
                "EFA-JSON datasource requires 'language' to be one of "
                f"{', '.join(EfaJsonServiceAlertsTransformer.SUPPORTED_LANGUAGES)}"
            )

        if "filter" in self.config and self.config["filter"]:
            if not isinstance(self.config["filter"], str):
                raise ValueError("'filter' must be a string")

    async def _fetch_records(self) -> dict[str, Any]:
        endpoint_url = self.config["endpoint"]
        response = None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
        }
        try:
            logger.info("[EfaJsonDatasource] Fetching EFA-JSON feed from %s", endpoint_url)
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(endpoint_url, headers=request_headers)
                response.raise_for_status()
                response_text = response.text
        
        except httpx.HTTPError as exc:
            logger.error("[EfaJsonDatasource] HTTP error fetching feed: %s", exc)
            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=endpoint_url,
                request_headers=request_headers,
                response_headers=dict(response.headers) if response and response.headers else None,
                response_status_code=response.status_code if response is not None else 404,
                response_content=str(exc),
                response_content_type="text/plain",
            )
            
            raise ValueError(f"Failed to fetch EFA-JSON feed: {exc}") from exc

        return await self._parse_and_transform_json(
            response_text,
            request_url=str(response.url),
            request_headers=request_headers,
            response_headers=dict(response.headers) if response.headers else None,
            response_status_code=response.status_code,
            source_name=self.config.get("_source_name", "efa-json"),
        )

    async def _fetch_records_from_payload(
        self, payload: bytes, content_type: str | None
    ) -> dict[str, Any]:
        """Parse and transform an already-provided EFA-JSON payload."""
        request_headers = {"Content-Type": content_type} if content_type else None
        
        return await self._parse_and_transform_json(
            payload,
            request_url="",
            request_headers=request_headers,
            response_headers=None,
            response_status_code=200,
            source_name=self.config.get("_source_name", "efa-json"),
            response_content_type=content_type,
        )

    async def _parse_and_transform_json(
        self,
        payload: bytes | str,
        *,
        request_url: str,
        request_headers: dict[str, str] | None,
        response_headers: dict[str, str] | None,
        response_status_code: int,
        source_name: str,
        response_content_type: str | None = None,
    ) -> dict[str, Any]:
        try:
            response_text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        except UnicodeDecodeError as exc:
            logger.error("[EfaJsonDatasource] Failed to decode JSON payload: %s", exc)
            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=request_url,
                request_headers=request_headers,
                response_headers=response_headers,
                response_status_code=422,
                response_content=str(exc),
                response_content_type="text/plain",
            )
            
            raise ValueError(f"Failed to decode EFA-JSON payload: {exc}") from exc

        try:
            response = await self._run_cpu_bound(json.loads, response_text)
        except json.JSONDecodeError as exc:
            logger.error("[EfaJsonDatasource] Failed to parse JSON payload: %s", exc)
            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=request_url,
                request_headers=request_headers,
                response_headers=response_headers,
                response_status_code=500,
                response_content=str(exc),
                response_content_type="text/plain",
            )
            
            raise ValueError(f"Failed to parse EFA-JSON payload: {exc}") from exc

        await self._log_request(
            source_id=self.config.get("_source_id"),
            request_url=request_url,
            request_headers=request_headers,
            response_headers=response_headers,
            response_status_code=response_status_code,
            response_content=response_text,
            response_content_type=response_content_type or "application/json",
        )

        return await self._transform_response(
            response,
            source_name=source_name,
            request_url=request_url,
            request_headers=request_headers,
            response_headers=response_headers,
        )

    async def _transform_response(
        self,
        response: Any,
        *,
        source_name: str,
        request_url: str,
        request_headers: dict[str, str] | None,
        response_headers: dict[str, str] | None,
    ) -> dict[str, Any]:
        """Transform decoded EFA-JSON response data to service-alert records."""
        dialect = EfaJsonDialect(self.config["dialect"])
        if dialect == EfaJsonDialect.ADDINFO:
            transformer = EfaJsonServiceAlertsTransformer(
                make_unique_id=self._make_unique_id,
                language=self.config["language"],
                filters=self.get_filters(),
            )
        else:
            raise ValueError(f"Unknown EFA-JSON dialect: {dialect}")

        try:
            records = await self._run_cpu_bound(
                transformer.transform,
                {"response": response, "source_name": source_name},
            )
        except Exception as exc:
            logger.error(
                "[EfaJsonDatasource] Failed to transform payload: %s",
                exc,
                exc_info=True,
            )
            
            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=request_url,
                request_headers=request_headers,
                response_headers=response_headers,
                response_status_code=500,
                response_content=str(exc),
                response_content_type="text/plain",
            )
            
            raise ValueError(f"Failed to transform EFA-JSON payload: {exc}") from exc

        return {
            "record_type": "service_alerts",
            "records": records,
            "_transform_runtime_ms": transformer.get_runtime_duration_ms(),
        }
