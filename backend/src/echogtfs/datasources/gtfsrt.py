"""GTFS-Realtime datasource for service-alert import."""

from __future__ import annotations

from enum import Enum
import json
import logging
from typing import Any

import httpx
from google.protobuf.json_format import MessageToDict

from echogtfs import gtfs_realtime_pb2
from echogtfs.datasources.base import DatasourceBase
from echogtfs.datasources.transformers import GtfsRtServiceAlertsTransformer

logger = logging.getLogger("uvicorn")


class GtfsRtDialect(str, Enum):
    GTFSRT_SERVICEALERTS = "gtfsrt-servicealerts"


class GtfsRealtimeDatasource(DatasourceBase):
    """Datasource implementation for GTFS-Realtime feeds."""

    CONFIG_SCHEMA: list[dict[str, Any]] = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "adapter.gtfsrt.endpoint.label",
            "required": True,
            "placeholder": "adapter.gtfsrt.endpoint.placeholder",
            "help_text": "adapter.gtfsrt.endpoint.help_text",
        },
        {
            "name": "token",
            "type": "password",
            "label": "adapter.gtfsrt.token.label",
            "required": False,
            "placeholder": "adapter.gtfsrt.token.placeholder",
            "help_text": "adapter.gtfsrt.token.help_text",
        },
        {
            "name": "dialect",
            "type": "enum",
            "label": "adapter.gtfsrt.dialect.label",
            "required": True,
            "options": ["gtfsrt-servicealerts"],
            "help_text": "adapter.gtfsrt.dialect.help_text",
        },
    ]

    def get_datasource_type(self) -> str:
        return "gtfsrt"

    def _validate_config(self) -> None:
        if "endpoint" not in self.config:
            raise ValueError("GtfsRt datasource requires 'endpoint' in config")

        if not isinstance(self.config["endpoint"], str):
            raise ValueError("'endpoint' must be a string")

        if "dialect" not in self.config:
            raise ValueError("GtfsRt datasource requires 'dialect' in config")

        try:
            GtfsRtDialect(self.config["dialect"])
        except ValueError:
            valid_dialects = [dialect.value for dialect in GtfsRtDialect]
            raise ValueError(
                f"Invalid dialect '{self.config['dialect']}'. "
                f"Valid options: {', '.join(valid_dialects)}"
            )

        if "token" in self.config and self.config["token"] is not None:
            if not isinstance(self.config["token"], str):
                raise ValueError("'token' must be a string")

    async def _fetch_records(self) -> dict[str, Any] | list[dict[str, Any]]:
        """Fetch GTFS-RT feed and transform entities into internal alert dicts."""
        from echogtfs.services.database import get_repository
        from echogtfs.services.datalog import DatalogService

        dialect = GtfsRtDialect(self.config["dialect"])

        endpoint = self.config["endpoint"]
        token = self.config.get("token", "").strip()

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        logger.info(f"[GtfsRealtimeDatasource] Fetching GTFS-RT feed from {endpoint}")

        response = None
        final_url = endpoint

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(endpoint, headers=headers)
                final_url = str(response.url)

                if final_url != endpoint:
                    logger.info(f"[GtfsRealtimeDatasource] Redirected to: {final_url}")

                response.raise_for_status()
                protobuf_data = response.content
        except httpx.HTTPError as exc:
            logger.error(f"[GtfsRealtimeDatasource] HTTP error fetching feed: {exc}")
            source_id = self.config.get("_source_id")
            if source_id and response is not None:
                try:
                    error_content = response.text if response.text else f"HTTP Error: {exc}"
                    await DatalogService(get_repository()).create_log_entry(
                        data_source_id=source_id,
                        request_url=final_url,
                        response_content=error_content,
                        request_headers=dict(headers) if headers else None,
                        response_headers=dict(response.headers) if response.headers else None,
                        response_mimetype="text/plain",
                        status_code=response.status_code if hasattr(response, "status_code") else None,
                    )
                except Exception as log_error:
                    logger.warning(
                        f"[GtfsRealtimeDatasource] Failed to log error request: {log_error}"
                    )
            raise ValueError(f"Failed to fetch GTFS-RT feed: {exc}")

        feed = gtfs_realtime_pb2.FeedMessage()
        try:
            feed.ParseFromString(protobuf_data)
        except Exception as exc:
            logger.error(f"[GtfsRealtimeDatasource] Failed to parse protobuf: {exc}")
            raise ValueError(f"Failed to parse GTFS-RT protobuf: {exc}")

        source_id = self.config.get("_source_id")
        if source_id:
            try:
                feed_dict = MessageToDict(feed, preserving_proto_field_name=True)
                feed_json = json.dumps(feed_dict, indent=2, ensure_ascii=False)
                await DatalogService(get_repository()).create_log_entry(
                    data_source_id=source_id,
                    request_url=final_url,
                    response_content=feed_json,
                    request_headers=dict(headers) if headers else None,
                    response_headers=dict(response.headers),
                    response_mimetype="application/json",
                    status_code=response.status_code,
                )
            except Exception as exc:
                logger.error(
                    f"[GtfsRealtimeDatasource] Failed to log request: {exc}",
                    exc_info=True,
                )

        if dialect == GtfsRtDialect.GTFSRT_SERVICEALERTS:
            transformer = GtfsRtServiceAlertsTransformer(make_unique_id=self._make_unique_id)
        else:
            raise ValueError(f"Unknown GTFS-RT dialect: {dialect}")

        records = transformer.transform(
            {
                "feed": feed,
                "source_name": self.config.get("_source_name", "gtfsrt"),
            }
        )

        return {
            "record_type": "service_alerts",
            "records": records,
        }
