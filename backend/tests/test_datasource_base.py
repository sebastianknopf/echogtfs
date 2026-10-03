from __future__ import annotations

from datetime import datetime, timezone
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _service_test_bootstrap  # noqa: F401

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")

from echogtfs.datasources.base import DatasourceBase
from echogtfs.enum.gtfsrt import AssignmentType
from echogtfs.enum.system import IncorrectStopIdHandling, InvalidReferencePolicy


class _TestDatasource(DatasourceBase):
    def _validate_config(self) -> None:
        return None

    async def _fetch_records(self):
        return self.config.get("_payload", {"record_type": "service_alerts", "records": []})

    async def _fetch_records_from_payload(self, payload: bytes, content_type: str | None):
        return self.config.get("_payload", {"record_type": "service_alerts", "records": []})


class _SystemRepositoryStub:
    def __init__(self):
        self.get_data_source_invalid_reference_policy = AsyncMock(
            return_value=InvalidReferencePolicy.DISCARD_INVALID
        )
        self.get_data_source_is_differential_updates = AsyncMock(return_value=False)
        self.list_data_source_mappings_grouped = AsyncMock(return_value={})
        self.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"trip-1"}}
        )


class _RealtimeRepositoryStub:
    def __init__(self):
        self.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"trip-1"}}
        )
        self.list_service_alerts_for_data_source = AsyncMock(return_value=[])
        self.list_service_alerts_by_ids = AsyncMock(return_value=[])
        self.delete_service_alerts_for_data_source_by_ids = AsyncMock()
        self.delete_service_alerts_by_ids = AsyncMock()
        self.upsert_service_alert_from_sync = AsyncMock()
        self.list_trips_for_data_source = AsyncMock(return_value=[])
        self.list_trips_by_ids = AsyncMock(return_value=[])
        self.list_trips_by_trip_ids = AsyncMock(return_value=[])
        self.delete_trips_by_trip_ids = AsyncMock()
        self.list_trip_ids_with_stop_events = AsyncMock(return_value=set())
        self.list_stop_events_for_trip = AsyncMock(return_value=[])
        self.delete_trips_for_data_source_by_ids = AsyncMock()
        self.update_trip_update_from_sync = AsyncMock()
        self.list_vehicles_for_data_source = AsyncMock(return_value=[])
        self.list_vehicles_by_ids = AsyncMock(return_value=[])
        self.delete_vehicles_for_data_source_by_ids = AsyncMock()
        self.update_vehicle_position_from_sync = AsyncMock()


class _GtfsRepositoryStub:
    def __init__(self):
        self.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}, "trip": {"trip-1"}}
        )
        self.get_gtfs_trip_with_stop_times = AsyncMock(return_value=None)




class TestDatasourceBase(unittest.TestCase):
    def setUp(self):
        self.datasource = _TestDatasource({})

    def test_make_unique_id_is_deterministic_for_non_uuid(self):
        self.assertEqual(self.datasource._make_unique_id("alert-1", "src"), self.datasource._make_unique_id("alert-1", "src"))

    def test_make_unique_id_keeps_uuid(self):
        original = "f5d3f5ec-f6ca-4d16-9330-f6691a53b4c8"
        self.assertEqual(str(self.datasource._make_unique_id(original, "src")), original)

    def test_get_filters_returns_empty_filter_classes(self):
        self.assertEqual(
            self.datasource.get_filters(),
            {"line": [], "operator": [], "legacy": []},
        )

    def test_get_filters_parses_comma_separated_values(self):
        self.datasource.config["filter"] = "line/LINE-*,operator/OP-*,legacy-*"

        self.assertEqual(
            self.datasource.get_filters(),
            {
                "line": ["LINE-*"],
                "operator": ["OP-*"],
                "legacy": ["legacy-*"],
            },
        )

    def test_get_filters_parses_whitespace_separated_values(self):
        self.datasource.config["filter"] = "line/LINE-* operator/OP-* legacy-*"

        self.assertEqual(
            self.datasource.get_filters(),
            {
                "line": ["LINE-*"],
                "operator": ["OP-*"],
                "legacy": ["legacy-*"],
            },
        )

    def test_get_filters_parses_mixed_separators_and_ignores_empty_values(self):
        self.datasource.config["filter"] = (
            " line/LINE-1,  operator/OP-1\tlegacy-1\n"
            "line/LINE-2,,operator/OP-2 "
        )

        self.assertEqual(
            self.datasource.get_filters(),
            {
                "line": ["LINE-1", "LINE-2"],
                "operator": ["OP-1", "OP-2"],
                "legacy": ["legacy-1"],
            },
        )
