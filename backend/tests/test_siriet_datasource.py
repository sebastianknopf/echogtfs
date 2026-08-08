from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.datasources import siriet as siriet_module
from echogtfs.datasources.siriet import SiriEtDatasource


class TestSirietDatasource(unittest.IsolatedAsyncioTestCase):
    def test_config_schema_includes_stop_handling_options(self):
        schema_names = {field["name"] for field in SiriEtDatasource.get_config_schema()}
        self.assertIn("treat_unexpected_stop_as_added_stop", schema_names)
        self.assertIn("treat_missing_stop_as_canceled_stop", schema_names)

    def test_stop_handling_options_default_to_false_and_are_required(self):
        datasource = SiriEtDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "siriet",
            }
        )

        self.assertFalse(datasource.config["treat_unexpected_stop_as_added_stop"])
        self.assertFalse(datasource.config["treat_missing_stop_as_canceled_stop"])

        schema = {field["name"]: field for field in SiriEtDatasource.get_config_schema()}
        self.assertTrue(schema["treat_unexpected_stop_as_added_stop"]["required"])
        self.assertTrue(schema["treat_missing_stop_as_canceled_stop"]["required"])

    def test_validate_config_rejects_missing_participantref(self):
        with self.assertRaises(ValueError):
            SiriEtDatasource(
                {
                    "endpoint": "https://x/{participantRef}",
                    "method": "request/response",
                    "dialect": "siriet",
                }
            )

    def test_build_request_xml_uses_estimated_timetable_request(self):
        datasource = SiriEtDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "siriet",
            }
        )

        xml_payload = datasource._build_request_xml()

        self.assertIn("EstimatedTimetableRequest", xml_payload)
        self.assertNotIn("SituationExchangeRequest", xml_payload)

    async def test_fetch_records_wraps_transformer_output(self):
        datasource = SiriEtDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "siriet",
            }
        )
        root = ET.fromstring("<root />")

        with patch.object(datasource, "_fetch_and_parse_xml", AsyncMock(return_value=root)), patch(
            "echogtfs.datasources.siriet.SiriEtTripUpdatesTransformer"
        ) as transformer_cls:
            transformer_cls.return_value.transform.return_value = [{"id": "e"}]
            transformer_cls.return_value.get_runtime_duration_ms.return_value = 12.5
            payload = await datasource._fetch_records()

        self.assertEqual(payload["record_type"], "trip_updates")
        self.assertEqual(payload["records"], [{"id": "e"}])
        self.assertEqual(payload["_transform_runtime_ms"], 12.5)
        self.assertFalse(datasource.config["treat_unexpected_stop_as_added_stop"])
        self.assertFalse(datasource.config["treat_missing_stop_as_canceled_stop"])

    async def test_fetch_records_raises_when_transform_fails(self):
        datasource = SiriEtDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "siriet",
            }
        )
        root = ET.fromstring("<root />")

        with patch.object(datasource, "_fetch_and_parse_xml", AsyncMock(return_value=root)), patch(
            "echogtfs.datasources.siriet.SiriEtTripUpdatesTransformer"
        ) as transformer_cls, patch.object(siriet_module.logger, "error"):
            transformer_cls.return_value.transform.side_effect = RuntimeError("transform failed")
            with self.assertRaises(ValueError):
                await datasource._fetch_records()
