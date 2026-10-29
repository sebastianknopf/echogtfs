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
from echogtfs.datasources import vdv454 as vdv454_module
from echogtfs.datasources.vdv454 import Vdv454Datasource


def _config(**overrides):
    config = {
        "endpoint": "https://x/{producerRef}/{participantRef}",
        "subscriberref": "P1",
        "producerref": "PROD1",
        "dialect": "vdv454_31",
    }
    config.update(overrides)
    return config


class TestVdv454Datasource(unittest.IsolatedAsyncioTestCase):
    def test_registered_as_subscription_datasource(self):
        self.assertIs(DATASOURCE_REGISTRY["vdv454"], Vdv454Datasource)
        self.assertTrue(issubclass(Vdv454Datasource, SubscriptionDatasourceBase))

    def test_config_schema_fields(self):
        schema = {field["name"]: field for field in Vdv454Datasource.get_config_schema()}

        self.assertNotIn("consumerendpoint", schema)
        self.assertTrue(schema["producerref"]["required"])
        self.assertEqual(schema["producerref"]["type"], schema["subscriberref"]["type"])
        self.assertEqual(schema["dialect"]["options"], ["vdv454_31"])
        for name in (
            "endpoint",
            "subscriberref",
            "dialect",
            "treat_unexpected_stop_as_added_stop",
            "treat_missing_stop_as_canceled_stop",
            "incorrect_stop_id_handling",
            "filter",
        ):
            self.assertIn(name, schema)

    def test_producerref_follows_subscriberref_in_schema(self):
        names = [field["name"] for field in Vdv454Datasource.get_config_schema()]

        self.assertEqual(names.index("producerref"), names.index("subscriberref") + 1)

    def test_stop_handling_options_default_to_false(self):
        datasource = Vdv454Datasource(_config())

        self.assertFalse(datasource.config["treat_unexpected_stop_as_added_stop"])
        self.assertFalse(datasource.config["treat_missing_stop_as_canceled_stop"])

    def test_validate_config_rejects_missing_required_fields(self):
        for missing in ("endpoint", "subscriberref", "producerref", "dialect"):
            config = _config()
            del config[missing]
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                Vdv454Datasource(config)

    def test_validate_config_rejects_invalid_dialect(self):
        with self.assertRaises(ValueError):
            Vdv454Datasource(_config(dialect="unknown"))

    def test_validate_config_rejects_non_string_producerref(self):
        with self.assertRaises(ValueError):
            Vdv454Datasource(_config(producerref=5))

    def test_subscription_params(self):
        params = Vdv454Datasource(_config(endpoint="https://x/aus")).get_subscription_params()

        self.assertEqual(params["provider_url"], "https://x/aus")
        self.assertEqual(params["service"], "ET")
        self.assertEqual(params["requestor_ref"], "P1")
        self.assertEqual(params["producer_ref"], "PROD1")
        self.assertEqual(params["delivery_mode"], "fetched")
        self.assertTrue(params["incremental_updates"])
        self.assertNotIn("consumer_address", params)

    def test_subscription_filters_default_to_empty(self):
        params = Vdv454Datasource(_config()).get_subscription_params()

        self.assertEqual(params["filters"], {"operators": [], "lines": []})

    def test_subscription_filters_use_prefixed_values_only(self):
        datasource = Vdv454Datasource(
            _config(filter="line/de:123:456, line/de:789:000 operator/OP1 operator/OP2 legacy_value")
        )

        self.assertEqual(
            datasource.get_subscription_params()["filters"],
            {"operators": ["OP1", "OP2"], "lines": ["de:123:456", "de:789:000"]},
        )

    def test_subscription_filters_ignore_legacy_filters(self):
        datasource = Vdv454Datasource(_config(filter="legacy1 legacy2"))

        self.assertEqual(datasource._get_subscription_filters(), {"operators": [], "lines": []})

    async def test_fetch_records_is_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            await Vdv454Datasource(_config())._fetch_records()

    async def test_payload_wraps_transformer_output(self):
        datasource = Vdv454Datasource(_config())

        with patch.object(
            datasource, "_parse_and_log_xml_payload", AsyncMock(return_value=ET.fromstring("<root />"))
        ), patch("echogtfs.datasources.vdv454.Vdv454V31TripUpdatesTransformer") as transformer_cls:
            transformer_cls.return_value.transform.return_value = [{"id": "e"}]
            transformer_cls.return_value.get_runtime_duration_ms.return_value = 12.5
            payload = await datasource._fetch_records_from_payload(b"<root />", "application/xml")

        self.assertEqual(payload["record_type"], "trip_updates")
        self.assertEqual(payload["records"], [{"id": "e"}])
        self.assertEqual(payload["_transform_runtime_ms"], 12.5)

    async def test_payload_raises_when_transform_fails(self):
        datasource = Vdv454Datasource(_config())

        with patch.object(
            datasource, "_parse_and_log_xml_payload", AsyncMock(return_value=ET.fromstring("<root />"))
        ), patch("echogtfs.datasources.vdv454.Vdv454V31TripUpdatesTransformer") as transformer_cls, patch.object(
            vdv454_module.logger, "error"
        ), patch.object(datasource, "_log_request", AsyncMock()):
            transformer_cls.return_value.transform.side_effect = RuntimeError("transform failed")
            with self.assertRaises(ValueError):
                await datasource._fetch_records_from_payload(b"<root />", "application/xml")
