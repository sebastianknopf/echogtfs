from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _service_test_bootstrap  # noqa: F401

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from echogtfs.enum.gtfsrt import AssignmentType
from echogtfs.enum.system import IncorrectStopIdHandling, InvalidReferencePolicy
from _realtime_processing_test_support import _SystemRepositoryStub, _RealtimeRepositoryStub, _GtfsRepositoryStub, make_processor
from echogtfs.services.realtime_processing.base import RealtimeProcessingServiceBase

class TestRealtimeProcessingServiceBase(unittest.TestCase):
    def setUp(self):
        self.datasource = make_processor(RealtimeProcessingServiceBase)

    def setUp(self):
        self.datasource = _TestDatasource({})
    def test_make_unique_id_is_deterministic_for_non_uuid(self):
        value_a = self.datasource._make_unique_id("alert-1", "src")
        value_b = self.datasource._make_unique_id("alert-1", "src")
        self.assertEqual(value_a, value_b)
    def test_make_unique_id_keeps_uuid(self):
        original = "f5d3f5ec-f6ca-4d16-9330-f6691a53b4c8"
        self.assertEqual(str(self.datasource._make_unique_id(original, "src")), original)
    def test_normalize_payload_accepts_envelope(self):
        record_type, records = self.datasource._normalize_fetched_payload(
            {"record_type": "service_alerts", "records": [{"id": 1}]}
        )
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
    def test_entity_validation_flags_include_per_reference_booleans(self):
        flags = self.datasource._entity_validation_flags(
            {"agency_id": "a1", "route_id": "missing", "stop_id": None, "trip_id": "trip-1"},
            {"agency": {"a1"}, "route": {"r1"}, "stop": {"s1"}},
        )

        self.assertTrue(flags["is_agency_valid"])
        self.assertFalse(flags["is_route_valid"])
        self.assertTrue(flags["is_stop_valid"])
        self.assertTrue(flags["is_trip_valid"])
        self.assertNotIn("is_valid", flags)
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
