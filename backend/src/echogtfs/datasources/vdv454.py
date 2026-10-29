"""VDV454-AUS datasource for trip-update data import."""

from __future__ import annotations

from enum import Enum
import logging
import xml.etree.ElementTree as ET
from typing import Any

from echogtfs.datasources.subscription_datasource_base import SubscriptionDatasourceBase
from echogtfs.datasources.transformers import Vdv454V31TripUpdatesTransformer
from echogtfs.enum.system import IncorrectStopIdHandling

logger = logging.getLogger("uvicorn")


class Vdv454Dialect(str, Enum):
    VDV454_31 = "vdv454_31"


class Vdv454Datasource(SubscriptionDatasourceBase):
    """Datasource implementation for VDV454-AUS feeds."""

    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "adapter.vdv454.endpoint.label",
            "required": True,
            "placeholder": "adapter.vdv454.endpoint.placeholder",
            "help_text": "adapter.vdv454.endpoint.help_text",
        },
        {
            "name": "subscriberref",
            "type": "text",
            "label": "adapter.vdv454.subscriberref.label",
            "required": True,
            "placeholder": "adapter.vdv454.subscriberref.placeholder",
            "help_text": "adapter.vdv454.subscriberref.help_text",
        },
        {
            "name": "producerref",
            "type": "text",
            "label": "adapter.vdv454.producerref.label",
            "required": True,
            "placeholder": "adapter.vdv454.producerref.placeholder",
            "help_text": "adapter.vdv454.producerref.help_text",
        },
        {
            "name": "dialect",
            "type": "enum",
            "label": "adapter.vdv454.dialect.label",
            "required": True,
            "options": ["vdv454_31"],
            "help_text": "adapter.vdv454.dialect.help_text",
        },
        {
            "name": "treat_unexpected_stop_as_added_stop",
            "type": "boolean",
            "label": "adapter.vdv454.treat_unexpected_stop_as_added_stop.label",
            "required": True,
            "help_text": "adapter.vdv454.treat_unexpected_stop_as_added_stop.help_text",
        },
        {
            "name": "treat_missing_stop_as_canceled_stop",
            "type": "boolean",
            "label": "adapter.vdv454.treat_missing_stop_as_canceled_stop.label",
            "required": True,
            "help_text": "adapter.vdv454.treat_missing_stop_as_canceled_stop.help_text",
        },
        {
            "name": "incorrect_stop_id_handling",
            "type": "enum",
            "label": "adapter.vdv454.incorrect_stop_id_handling.label",
            "required": True,
            "options": [
                IncorrectStopIdHandling.IGNORE.value,
                IncorrectStopIdHandling.FIX_TO_NOMINAL_STOP_ID.value,
            ],
            "help_text": "adapter.vdv454.incorrect_stop_id_handling.help_text",
        },
        {
            "name": "filter",
            "type": "taglist",
            "label": "adapter.vdv454.filter.label",
            "required": False,
            "placeholder": "adapter.vdv454.filter.placeholder",
            "help_text": "adapter.vdv454.filter.help_text",
        },
    ]

    def _validate_config(self) -> None:
        self.config.setdefault("treat_unexpected_stop_as_added_stop", False)
        self.config.setdefault("treat_missing_stop_as_canceled_stop", False)
        self.config.setdefault("incorrect_stop_id_handling", IncorrectStopIdHandling.IGNORE.value)

        is_event_based = self._is_event_based_execution()

        for field_name in ("endpoint", "subscriberref", "producerref"):
            value = self.config.get(field_name)
            if not value:
                if not is_event_based:
                    raise ValueError(f"Vdv454 datasource requires '{field_name}' in config")
            elif not isinstance(value, str):
                raise ValueError(f"'{field_name}' must be a string")

        if "dialect" not in self.config:
            raise ValueError("Vdv454 datasource requires 'dialect' in config")

        try:
            Vdv454Dialect(self.config["dialect"])
        except ValueError:
            valid_dialects = [dialect.value for dialect in Vdv454Dialect]
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

        try:
            IncorrectStopIdHandling(self.config.get("incorrect_stop_id_handling"))
        except ValueError:
            valid_values = [item.value for item in IncorrectStopIdHandling]
            raise ValueError(
                "'incorrect_stop_id_handling' must be one of: "
                f"{', '.join(valid_values)}"
            )

        if "filter" in self.config and self.config["filter"]:
            if not isinstance(self.config["filter"], str):
                raise ValueError("'filter' must be a string")

    async def _fetch_records(self) -> dict[str, Any]:
        raise NotImplementedError(
            "The VDV454 datasource does not support fetching; use push or subscription delivery"
        )

    async def _fetch_records_from_payload(self, payload: bytes, content_type: str | None) -> dict[str, Any]:
        """Parse an already-provided VDV454 payload (push API)."""
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
        source_name = self.config.get("_source_name", "vdv454")
        self.config["treat_unexpected_stop_as_added_stop"] = bool(
            self.config.get("treat_unexpected_stop_as_added_stop", False)
        )
        self.config["treat_missing_stop_as_canceled_stop"] = bool(
            self.config.get("treat_missing_stop_as_canceled_stop", False)
        )
        self.config["incorrect_stop_id_handling"] = IncorrectStopIdHandling(
            self.config.get("incorrect_stop_id_handling", IncorrectStopIdHandling.IGNORE.value)
        ).value

        dialect = Vdv454Dialect(self.config["dialect"])
        if dialect == Vdv454Dialect.VDV454_31:
            transformer = Vdv454V31TripUpdatesTransformer(
                filters=self.get_filters(),
            )
        else:
            raise ValueError(f"Unknown VDV454 dialect: {dialect}")

        try:
            records = await self._run_cpu_bound(
                transformer.transform,
                {"root": root, "source_name": source_name},
            )
        except Exception as exc:
            logger.error(f"[Vdv454Datasource] Failed to transform payload: {exc}", exc_info=True)

            await self._log_request(
                source_id=self.config.get("_source_id"),
                request_url=request_url,
                request_headers=request_headers,
                response_headers=None,
                response_status_code=500,
                response_content=str(exc),
                response_content_type="text/plain",
            )

            raise ValueError(f"Failed to transform VDV454 payload: {exc}") from exc

        return {
            "record_type": "trip_updates",
            "records": records,
            "_transform_runtime_ms": transformer.get_runtime_duration_ms(),
        }

    def get_subscription_params(self) -> dict[str, Any]:
        """Return the parameters required to configure the subscription.

        The VDV454 subscription (AboAUS) is configured at the producer, so no consumer
        address is provided. The values follow the SIRI subscription parameter names; the
        VDV equivalents are noted for the subscription service.
        """
        return {
            "provider_url": self.config.get("endpoint"),
            "profile": "de-vdv",
            "version": "3.1",
            "service": "ET",
            "delivery_mode": "fetched",
            "requestor_ref": self.config.get("subscriberref"),
            "subscriber_ref": self.config.get("subscriberref"),
            "producer_ref": self.config.get("producerref"),
            "logging": False,
            "preview_interval": "PT2H",
            "initial_termination_time": "2999-12-31T23:59:00Z",
            "incremental_updates": True,
            "change_before_updates": "PT30S",
            "heartbeat": {
                "enabled": True,
                "timeout_seconds": 180,
                "check_status_enabled": False,
            },
        }
