"""VDV453-VIS datasource for vehicle-position data import."""

from __future__ import annotations

from enum import Enum
import logging
import xml.etree.ElementTree as ET
from typing import Any

from echogtfs.datasources.subscription_datasource_base import SubscriptionDatasourceBase
from echogtfs.datasources.transformers import Vdv453V31VehiclePositionsTransformer

logger = logging.getLogger("uvicorn")


class Vdv453Dialect(str, Enum):
    VDV453_31 = "vdv453_31"


class Vdv453Datasource(SubscriptionDatasourceBase):
    """Datasource implementation for VDV453-VIS feeds."""

    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "adapter.vdv453.endpoint.label",
            "required": True,
            "placeholder": "adapter.vdv453.endpoint.placeholder",
            "help_text": "adapter.vdv453.endpoint.help_text",
        },
        {
            "name": "subscriberref",
            "type": "text",
            "label": "adapter.vdv453.subscriberref.label",
            "required": True,
            "placeholder": "adapter.vdv453.subscriberref.placeholder",
            "help_text": "adapter.vdv453.subscriberref.help_text",
        },
        {
            "name": "producerref",
            "type": "text",
            "label": "adapter.vdv453.producerref.label",
            "required": True,
            "placeholder": "adapter.vdv453.producerref.placeholder",
            "help_text": "adapter.vdv453.producerref.help_text",
        },
        {
            "name": "dialect",
            "type": "enum",
            "label": "adapter.vdv453.dialect.label",
            "required": True,
            "options": ["vdv453_31"],
            "help_text": "adapter.vdv453.dialect.help_text",
        },
        {
            "name": "filter",
            "type": "taglist",
            "label": "adapter.vdv453.filter.label",
            "required": False,
            "placeholder": "adapter.vdv453.filter.placeholder",
            "help_text": "adapter.vdv453.filter.help_text",
        },
    ]

    def _validate_config(self) -> None:
        is_event_based = self._is_event_based_execution()

        for field_name in ("endpoint", "subscriberref", "producerref"):
            value = self.config.get(field_name)
            if not value:
                if not is_event_based:
                    raise ValueError(f"Vdv453 datasource requires '{field_name}' in config")
            elif not isinstance(value, str):
                raise ValueError(f"'{field_name}' must be a string")

        if "dialect" not in self.config:
            raise ValueError("Vdv453 datasource requires 'dialect' in config")

        try:
            Vdv453Dialect(self.config["dialect"])
        except ValueError:
            valid_dialects = [dialect.value for dialect in Vdv453Dialect]
            raise ValueError(
                f"Invalid dialect '{self.config['dialect']}'. Valid options: {', '.join(valid_dialects)}"
            )

        if "filter" in self.config and self.config["filter"]:
            if not isinstance(self.config["filter"], str):
                raise ValueError("'filter' must be a string")

    async def _fetch_records(self) -> dict[str, Any]:
        raise NotImplementedError(
            "The VDV453 datasource does not support fetching; use push or subscription delivery"
        )

    async def _fetch_records_from_payload(self, payload: bytes, content_type: str | None) -> dict[str, Any]:
        """Parse an already-provided VDV453 payload (push API)."""
        root = await self._parse_and_log_xml_payload(payload, content_type)
        request_headers = {"Content-Type": content_type} if content_type else None
        return await self._transform_root(root, request_url="", request_headers=request_headers)

    async def _transform_root(
        self,
        root: ET.Element,
        *,
        request_url: str,
        request_headers: dict[str, str] | None,
    ) -> dict[str, Any]:
        source_name = self.config.get("_source_name", "vdv453")

        dialect = Vdv453Dialect(self.config["dialect"])
        if dialect == Vdv453Dialect.VDV453_31:
            transformer = Vdv453V31VehiclePositionsTransformer(
                filters=self.get_filters(),
            )
        else:
            raise ValueError(f"Unknown VDV453 dialect: {dialect}")

        try:
            records = await self._run_cpu_bound(
                transformer.transform,
                {"root": root, "source_name": source_name},
            )
        except Exception as exc:
            logger.error(f"[Vdv453Datasource] Failed to transform payload: {exc}", exc_info=True)

            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=request_url,
                request_headers=request_headers,
                response_headers=None,
                response_status_code=500,
                response_content=str(exc),
                response_content_type="text/plain",
            )

            raise ValueError(f"Failed to transform VDV453 payload: {exc}") from exc

        return {
            "record_type": "vehicle_positions",
            "records": records,
            "_transform_runtime_ms": transformer.get_runtime_duration_ms(),
        }

    def _get_subscription_filters(self) -> dict[str, list[str]]:
        """Map prefixed line/operator filters to subscription filters; legacy filters are ignored."""
        filters = self.get_filters()

        return {
            "operators": list(filters["operator"]),
            "lines": list(filters["line"]),
        }

    def get_subscription_params(self) -> dict[str, Any]:
        """Return the parameters required to configure the subscription.

        The VDV453 subscription (AboVIS) is configured at the producer, so no consumer
        address is provided. The values follow the SIRI subscription parameter names; the
        VDV equivalents are noted for the subscription service.
        """
        return {
            "provider_url": self.config.get("endpoint"),
            "profile": "de-vdv",
            "version": "3.1",
            "service": "VM",
            "delivery_mode": "fetched",
            "subscriber_ref": self.config.get("subscriberref"),
            "producer_ref": self.config.get("producerref"),
            "vis_id": "ECHOGTFS",
            "logging": False,
            "initial_termination_time": "2999-12-31T23:59:00Z",
            "incremental_updates": True,
            "filters": self._get_subscription_filters(),
            "heartbeat": {
                "enabled": True,
                "timeout_seconds": 180,
                "check_status_enabled": False,
            },
            "parameters": {
                "visId": "1"
            }
        }
