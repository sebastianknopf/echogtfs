"""Datasource registry and factory."""

from __future__ import annotations

from typing import Any

from echogtfs.datasources.base import DatasourceBase
from echogtfs.datasources.gtfsrt import GtfsRealtimeDatasource
from echogtfs.datasources.siriet import SiriEtDatasource
from echogtfs.datasources.sirilite import SiriLiteDatasource
from echogtfs.datasources.sirivm import SiriVmDatasource
from echogtfs.datasources.sirisx import SiriSxDatasource

__all__ = [
    "DatasourceBase",
    "GtfsRealtimeDatasource",
    "SiriEtDatasource",
    "SiriLiteDatasource",
    "SiriVmDatasource",
    "SiriSxDatasource",
    "DATASOURCE_REGISTRY",
    "get_datasource",
]


DATASOURCE_REGISTRY: dict[str, type[DatasourceBase]] = {
    "gtfsrt": GtfsRealtimeDatasource,
    "sirilite": SiriLiteDatasource,
    "sirisx": SiriSxDatasource,
    "siriet": SiriEtDatasource,
    "sirivm": SiriVmDatasource,
}


def get_datasource(source_type: str, config: dict[str, Any]) -> DatasourceBase:
    """Create a datasource instance by its registered type."""
    datasource_class = DATASOURCE_REGISTRY.get(source_type.lower())
    if not datasource_class:
        raise ValueError(
            f"Unknown datasource type: {source_type}. "
            f"Available types: {', '.join(DATASOURCE_REGISTRY.keys())}"
        )

    return datasource_class(config)
