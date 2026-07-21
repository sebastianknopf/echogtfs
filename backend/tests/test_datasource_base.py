from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.datasources.base import DatasourceBase
from echogtfs.enum.system import InvalidReferencePolicy


class _TestDatasource(DatasourceBase):
    def _validate_config(self) -> None:
        return None

    async def _fetch_records(self):
        return self.config.get("_payload", [])


class _SystemRepositoryStub:
    def __init__(self):
        self.get_data_source_invalid_reference_policy = AsyncMock(
            return_value=InvalidReferencePolicy.DISCARD_INVALID
        )
        self.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}}
        )


class _RealtimeRepositoryStub:
    def __init__(self):
        self.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}}
        )
        self.list_service_alerts_for_data_source = AsyncMock(return_value=[])
        self.list_service_alerts_by_ids = AsyncMock(return_value=[])
        self.delete_service_alerts_for_data_source_by_ids = AsyncMock()
        self.delete_service_alerts_by_ids = AsyncMock()
        self.upsert_service_alert_from_sync = AsyncMock()


class _GtfsRepositoryStub:
    def __init__(self):
        self.list_gtfs_entity_ids = AsyncMock(
            return_value={"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}}
        )


class TestDatasourceBaseHelpers(unittest.TestCase):
    def setUp(self):
        self.datasource = _TestDatasource({})

    def test_make_unique_id_is_deterministic_for_non_uuid(self):
        value_a = self.datasource._make_unique_id("alert-1", "src")
        value_b = self.datasource._make_unique_id("alert-1", "src")
        self.assertEqual(value_a, value_b)

    def test_make_unique_id_keeps_uuid(self):
        original = "f5d3f5ec-f6ca-4d16-9330-f6691a53b4c8"
        self.assertEqual(str(self.datasource._make_unique_id(original, "src")), original)

    def test_normalize_payload_accepts_list(self):
        record_type, records = self.datasource._normalize_fetched_payload([{"id": 1}])
        self.assertEqual(record_type, "service_alerts")
        self.assertEqual(records, [{"id": 1}])

    def test_normalize_payload_rejects_invalid_shape(self):
        with self.assertRaises(ValueError):
            self.datasource._normalize_fetched_payload({"records": []})

    def test_validate_entity_rejects_trip_only(self):
        is_valid = self.datasource._validate_entity(
            {"trip_id": "T1", "agency_id": None, "route_id": None, "stop_id": None},
            {"agency": set(), "route": set(), "stop": set()},
        )
        self.assertFalse(is_valid)

    def test_validate_and_clean_entity_elements_removes_invalid_fields(self):
        cleaned, has_valid = self.datasource._validate_and_clean_entity_elements(
            {"agency_id": "unknown", "route_id": "r1", "stop_id": "s9"},
            {"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}},
        )
        self.assertTrue(has_valid)
        self.assertIsNone(cleaned["agency_id"])
        self.assertEqual(cleaned["route_id"], "r1")
        self.assertIsNone(cleaned["stop_id"])

    def test_deduplicate_entities(self):
        entities = [
            {
                "agency_id": "a1",
                "route_id": "r1",
                "route_type": None,
                "stop_id": None,
                "trip_id": None,
                "direction_id": None,
            },
            {
                "agency_id": "a1",
                "route_id": "r1",
                "route_type": None,
                "stop_id": None,
                "trip_id": None,
                "direction_id": None,
            },
        ]
        self.assertEqual(len(self.datasource._deduplicate_entities(entities)), 1)


class TestDatasourceBaseDeepSync(unittest.IsolatedAsyncioTestCase):
    async def test_sync_service_alert_records_applies_policy_and_upserts(self):
        repository = _SystemRepositoryStub()
        realtime_repository = _RealtimeRepositoryStub()
        gtfs_repository = _GtfsRepositoryStub()
        datasource = _TestDatasource({})
        datasource._identifier_mapping_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_mapping_count=lambda: 0,
            apply_mapping=lambda e: e,
        )
        datasource._entity_enrichment_service = SimpleNamespace(
            initialize=AsyncMock(),
            get_loaded_enrichment_count=lambda: 0,
            apply_enrichment=lambda _a, _b: None,
        )

        records = [
            {
                "id": "alert-1",
                "cause": "UNKNOWN_CAUSE",
                "effect": "UNKNOWN_EFFECT",
                "severity_level": "UNKNOWN_SEVERITY",
                "is_active": True,
                "translations": [],
                "active_periods": [],
                "informed_entities": [{"agency_id": "x", "route_id": None, "stop_id": None}],
            }
        ]

        result = await datasource._sync_service_alert_records(
            repository=repository,
            realtime_repository=realtime_repository,
            gtfs_repository=gtfs_repository,
            source_id=2,
            source_name="Demo",
            records=records,
        )

        self.assertEqual(result, {"added": 1, "updated": 0, "deleted": 0})
        realtime_repository.upsert_service_alert_from_sync.assert_awaited_once()
        kwargs = realtime_repository.upsert_service_alert_from_sync.await_args.kwargs
        self.assertEqual(kwargs["alert_id"], "alert-1")
        self.assertFalse(kwargs["is_active_on_create"])
        self.assertEqual(kwargs["informed_entities"], [])