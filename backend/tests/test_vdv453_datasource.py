from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _service_test_bootstrap  # noqa: F401

from echogtfs.datasources import DATASOURCE_REGISTRY, SubscriptionDatasourceBase
from echogtfs.datasources import vdv453 as vdv453_module
from echogtfs.datasources.vdv453 import Vdv453Datasource


def _config(**overrides):
    config = {
        "endpoint": "https://x/vis",
        "subscriberref": "P1",
        "producerref": "PROD1",
        "dialect": "vdv453_31",
    }
    config.update(overrides)
    return config


class TestVdv453Datasource(unittest.IsolatedAsyncioTestCase):
    def test_registered_as_subscription_datasource(self):
        self.assertIs(DATASOURCE_REGISTRY["vdv453"], Vdv453Datasource)
        self.assertTrue(issubclass(Vdv453Datasource, SubscriptionDatasourceBase))

    def test_config_schema_fields(self):
        schema = {field["name"]: field for field in Vdv453Datasource.get_config_schema()}

        self.assertEqual(schema["dialect"]["options"], ["vdv453_31"])
        for name in ("endpoint", "subscriberref", "producerref", "dialect", "filter"):
            self.assertIn(name, schema)
        self.assertNotIn("visid", schema)

    def test_validate_config_rejects_missing_required_fields(self):
        for missing in ("endpoint", "subscriberref", "producerref", "dialect"):
            config = _config()
            del config[missing]
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                Vdv453Datasource(config)

    def test_validate_config_rejects_invalid_dialect(self):
        with self.assertRaises(ValueError):
            Vdv453Datasource(_config(dialect="unknown"))

    def test_subscription_params(self):
        params = Vdv453Datasource(_config()).get_subscription_params()

        self.assertEqual(params["provider_url"], "https://x/vis")
        self.assertEqual(params["service"], "VM")
        self.assertEqual(params["vis_id"], "ECHOGTFS")
        self.assertEqual(params["producer_ref"], "PROD1")
        self.assertTrue(params["incremental_updates"])
        self.assertNotIn("consumer_address", params)

    def test_subscription_filters_use_prefixed_values_only(self):
        datasource = Vdv453Datasource(_config(filter="line/L1 operator/OP1 legacy"))

        self.assertEqual(
            datasource.get_subscription_params()["filters"],
            {"operators": ["OP1"], "lines": ["L1"]},
        )

    async def test_fetch_records_is_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            await Vdv453Datasource(_config())._fetch_records()

    async def test_payload_wraps_transformer_output(self):
        datasource = Vdv453Datasource(_config())

        with patch.object(
            datasource, "_parse_and_log_xml_payload", AsyncMock(return_value=ET.fromstring("<root />"))
        ), patch("echogtfs.datasources.vdv453.Vdv453V31VehiclePositionsTransformer") as transformer_cls:
            transformer_cls.return_value.transform.return_value = [{"id": "v"}]
            transformer_cls.return_value.get_runtime_duration_ms.return_value = 3.0
            payload = await datasource._fetch_records_from_payload(b"<root />", "application/xml")

        self.assertEqual(payload["record_type"], "vehicle_positions")
        self.assertEqual(payload["records"], [{"id": "v"}])
        self.assertEqual(payload["_transform_runtime_ms"], 3.0)

    async def test_payload_raises_when_transform_fails(self):
        datasource = Vdv453Datasource(_config())

        with patch.object(
            datasource, "_parse_and_log_xml_payload", AsyncMock(return_value=ET.fromstring("<root />"))
        ), patch("echogtfs.datasources.vdv453.Vdv453V31VehiclePositionsTransformer") as transformer_cls, patch.object(
            vdv453_module.logger, "error"
        ), patch.object(datasource, "_log_request", AsyncMock()):
            transformer_cls.return_value.transform.side_effect = RuntimeError("boom")
            with self.assertRaises(ValueError):
                await datasource._fetch_records_from_payload(b"<root />", "application/xml")
