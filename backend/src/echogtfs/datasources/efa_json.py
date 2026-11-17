"""EFA-JSON datasource placeholder."""

from __future__ import annotations

from typing import Any

from echogtfs.datasources.base import DatasourceBase


class EfaJsonDatasource(DatasourceBase):
    """Empty datasource frame for EFA-JSON feeds."""

    CONFIG_SCHEMA: list[dict[str, Any]] = []

    def get_datasource_type(self) -> str:
        return "efa-json"

    def _validate_config(self) -> None:
        pass

    async def _fetch_records(self) -> dict[str, Any]:
        raise NotImplementedError("EFA-JSON datasource is not implemented")

    async def _fetch_records_from_payload(
        self, payload: bytes, content_type: str | None
    ) -> dict[str, Any]:
        raise NotImplementedError("EFA-JSON datasource is not implemented")
