from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.datasources.sirisx import SiriSxDatasource
from echogtfs.datasources import sirisx as sirisx_module


class TestSirisxDatasource(unittest.IsolatedAsyncioTestCase):
    def test_validate_config_rejects_missing_participantref(self):
        with self.assertRaises(ValueError):
            SiriSxDatasource(
                {
                    "endpoint": "https://x/{participantRef}",
                    "method": "request/response",
                    "dialect": "sirisx",
                }
            )

    async def test_fetch_records_wraps_transformer_output(self):
        datasource = SiriSxDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "sirisx",
            }
        )
        root = ET.fromstring("<root />")

        with patch.object(datasource, "_fetch_and_parse_xml", AsyncMock(return_value=root)), patch(
            "echogtfs.datasources.sirisx.SiriSxServiceAlertsTransformer"
        ) as transformer_cls:
            transformer_cls.return_value.transform.return_value = [{"id": "c"}]
            payload = await datasource._fetch_records()

        self.assertEqual(payload["record_type"], "service_alerts")
        self.assertEqual(payload["records"], [{"id": "c"}])

    async def test_publish_subscribe_not_supported(self):
        datasource = SiriSxDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "P1",
                "method": "publish/subscribe",
                "dialect": "sirisx",
            }
        )

        with self.assertRaises(NotImplementedError):
            await datasource._fetch_and_parse_xml()

    async def test_fetch_records_raises_when_transform_fails(self):
        datasource = SiriSxDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "sirisx",
            }
        )
        root = ET.fromstring("<root />")

        with patch.object(datasource, "_fetch_and_parse_xml", AsyncMock(return_value=root)), patch(
            "echogtfs.datasources.sirisx.SiriSxServiceAlertsTransformer"
        ) as transformer_cls, patch.object(sirisx_module.logger, "error"):
            transformer_cls.return_value.transform.side_effect = RuntimeError("transform failed")
            with self.assertRaises(ValueError):
                await datasource._fetch_records()