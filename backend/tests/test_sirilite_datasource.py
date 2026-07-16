from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.datasources.sirilite import SiriLiteDatasource
from echogtfs.datasources import sirilite as sirilite_module


class TestSiriliteDatasource(unittest.IsolatedAsyncioTestCase):
    def test_validate_config_rejects_unknown_dialect(self):
        with self.assertRaises(ValueError):
            SiriLiteDatasource({"endpoint": "https://x", "dialect": "unknown"})

    async def test_fetch_records_wraps_transformer_output(self):
        datasource = SiriLiteDatasource({"endpoint": "https://x", "dialect": "swiss"})
        root = ET.fromstring("<root />")

        with patch.object(datasource, "_fetch_and_parse_xml", AsyncMock(return_value=root)), patch(
            "echogtfs.datasources.sirilite.SiriLiteSwissServiceAlertsTransformer"
        ) as transformer_cls:
            transformer_cls.return_value.transform.return_value = [{"id": "b"}]
            payload = await datasource._fetch_records()

        self.assertEqual(payload["record_type"], "service_alerts")
        self.assertEqual(payload["records"], [{"id": "b"}])

    async def test_fetch_records_raises_when_transform_fails(self):
        datasource = SiriLiteDatasource({"endpoint": "https://x", "dialect": "swiss"})
        root = ET.fromstring("<root />")

        with patch.object(datasource, "_fetch_and_parse_xml", AsyncMock(return_value=root)), patch(
            "echogtfs.datasources.sirilite.SiriLiteSwissServiceAlertsTransformer"
        ) as transformer_cls, patch.object(sirilite_module.logger, "error"):
            transformer_cls.return_value.transform.side_effect = RuntimeError("transform failed")
            with self.assertRaises(ValueError):
                await datasource._fetch_records()