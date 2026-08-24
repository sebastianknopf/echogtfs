from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    import _service_test_bootstrap  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - depends on unittest discovery mode
    from tests import _service_test_bootstrap  # noqa: F401

from echogtfs.datasources.sirilite import SiriLiteDatasource
from echogtfs.datasources import sirilite as sirilite_module


class TestSiriliteDatasource(unittest.IsolatedAsyncioTestCase):
    def test_config_schema_includes_stop_handling_options(self):
        schema_names = {field["name"] for field in SiriLiteDatasource.get_config_schema()}
        self.assertIn("treat_unexpected_stop_as_added_stop", schema_names)
        self.assertIn("treat_missing_stop_as_canceled_stop", schema_names)

    def test_stop_handling_options_default_to_false_and_are_required(self):
        datasource = SiriLiteDatasource({"endpoint": "https://x", "dialect": "sirisx-swiss"})

        self.assertFalse(datasource.config["treat_unexpected_stop_as_added_stop"])
        self.assertFalse(datasource.config["treat_missing_stop_as_canceled_stop"])

        schema = {field["name"]: field for field in SiriLiteDatasource.get_config_schema()}
        self.assertTrue(schema["treat_unexpected_stop_as_added_stop"]["required"])
        self.assertTrue(schema["treat_missing_stop_as_canceled_stop"]["required"])

    def test_validate_config_rejects_unknown_dialect(self):
        with self.assertRaises(ValueError):
            SiriLiteDatasource({"endpoint": "https://x", "dialect": "unknown"})

    async def test_fetch_records_wraps_transformer_output_for_trip_updates(self):
        datasource = SiriLiteDatasource({"endpoint": "https://x", "dialect": "siriet"})
        root = ET.fromstring("<root />")

        with patch.object(datasource, "_fetch_and_parse_xml", AsyncMock(return_value=root)), patch(
            "echogtfs.datasources.sirilite.SiriEtTripUpdatesTransformer"
        ) as transformer_cls:
            transformer_cls.return_value.transform.return_value = [{"id": "b"}]
            transformer_cls.return_value.get_runtime_duration_ms.return_value = 8.25
            payload = await datasource._fetch_records()

        self.assertEqual(payload["record_type"], "trip_updates")
        self.assertEqual(payload["records"], [{"id": "b"}])
        self.assertEqual(payload["_transform_runtime_ms"], 8.25)
        self.assertFalse(datasource.config["treat_unexpected_stop_as_added_stop"])
        self.assertFalse(datasource.config["treat_missing_stop_as_canceled_stop"])

    async def test_fetch_records_raises_when_transform_fails(self):
        datasource = SiriLiteDatasource({"endpoint": "https://x", "dialect": "sirisx-swiss"})
        root = ET.fromstring("<root />")

        with patch.object(datasource, "_fetch_and_parse_xml", AsyncMock(return_value=root)), patch(
            "echogtfs.datasources.sirilite.SiriSxSwissServiceAlertsTransformer"
        ) as transformer_cls, patch.object(sirilite_module.logger, "error"):
            transformer_cls.return_value.transform.side_effect = RuntimeError("transform failed")
            with self.assertRaises(ValueError):
                await datasource._fetch_records()