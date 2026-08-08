from __future__ import annotations

import os
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")

from echogtfs.datasources import sirivm as sirivm_module
from echogtfs.datasources.sirivm import SiriVmDatasource


class TestSirivmDatasource(unittest.IsolatedAsyncioTestCase):
    def test_validate_config_rejects_missing_participantref(self):
        with self.assertRaises(ValueError):
            SiriVmDatasource(
                {
                    "endpoint": "https://x/{participantRef}",
                    "method": "request/response",
                    "dialect": "sirivm",
                }
            )

    def test_build_request_xml_uses_vehicle_monitoring_request_with_calls_detail(self):
        datasource = SiriVmDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "sirivm",
            }
        )

        xml_payload = datasource._build_request_xml()

        self.assertIn("VehicleMonitoringRequest", xml_payload)
        self.assertIn("VehicleMonitoringDetailLevel", xml_payload)
        self.assertIn("calls", xml_payload)
        self.assertIn("MaximumNumberOfCalls", xml_payload)
        self.assertNotIn("EstimatedTimetableRequest", xml_payload)
        self.assertNotIn("SituationExchangeRequest", xml_payload)

    async def test_fetch_records_wraps_transformer_output(self):
        datasource = SiriVmDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "sirivm",
            }
        )
        root = ET.fromstring("<root />")

        with patch.object(datasource, "_fetch_and_parse_xml", AsyncMock(return_value=root)), patch(
            "echogtfs.datasources.sirivm.SiriVmVehiclePositionsTransformer"
        ) as transformer_cls:
            transformer_cls.return_value.transform.return_value = [{"id": "v"}]
            transformer_cls.return_value.get_runtime_duration_ms.return_value = 9.75
            payload = await datasource._fetch_records()

        self.assertEqual(payload["record_type"], "vehicle_positions")
        self.assertEqual(payload["records"], [{"id": "v"}])
        self.assertEqual(payload["_transform_runtime_ms"], 9.75)

    async def test_publish_subscribe_not_supported(self):
        datasource = SiriVmDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "P1",
                "method": "publish/subscribe",
                "dialect": "sirivm",
            }
        )

        with self.assertRaises(NotImplementedError):
            await datasource._fetch_and_parse_xml()

    async def test_fetch_records_raises_when_transform_fails(self):
        datasource = SiriVmDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "sirivm",
            }
        )
        root = ET.fromstring("<root />")

        with patch.object(datasource, "_fetch_and_parse_xml", AsyncMock(return_value=root)), patch(
            "echogtfs.datasources.sirivm.SiriVmVehiclePositionsTransformer"
        ) as transformer_cls, patch.object(sirivm_module.logger, "error"):
            transformer_cls.return_value.transform.side_effect = RuntimeError("transform failed")
            with self.assertRaises(ValueError):
                await datasource._fetch_records()
