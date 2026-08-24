from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    import _service_test_bootstrap  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - depends on unittest discovery mode
    from tests import _service_test_bootstrap  # noqa: F401

from echogtfs.datasources.gtfsrt import GtfsRealtimeDatasource
from echogtfs.datasources import gtfsrt as gtfsrt_module


class TestGtfsrtDatasource(unittest.IsolatedAsyncioTestCase):
    def test_validate_config_rejects_missing_endpoint(self):
        with self.assertRaises(ValueError):
            GtfsRealtimeDatasource({"dialect": "gtfsrt-servicealerts"})

    async def test_fetch_records_wraps_transformer_output(self):
        datasource = GtfsRealtimeDatasource({"endpoint": "https://x", "dialect": "gtfsrt-servicealerts"})

        class _FakeResponse:
            url = "https://x"
            status_code = 200
            headers = {"Content-Type": "application/x-protobuf"}
            content = b"raw"

            def raise_for_status(self):
                return None

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, *_args, **_kwargs):
                return _FakeResponse()

        class _FakeFeed:
            def ParseFromString(self, _data):
                return None

        with patch("echogtfs.datasources.gtfsrt.httpx.AsyncClient", return_value=_FakeClient()), patch(
            "echogtfs.datasources.gtfsrt.gtfs_realtime_pb2.FeedMessage", return_value=_FakeFeed()
        ), patch("echogtfs.datasources.gtfsrt.MessageToDict", return_value={}), patch(
            "echogtfs.datasources.gtfsrt.GtfsRtServiceAlertsTransformer"
        ) as transformer_cls:
            transformer_cls.return_value.transform.return_value = [{"id": "a"}]
            payload = await datasource._fetch_records()

        self.assertEqual(payload["record_type"], "service_alerts")
        self.assertEqual(payload["records"], [{"id": "a"}])

    async def test_fetch_records_raises_when_transform_fails(self):
        datasource = GtfsRealtimeDatasource({"endpoint": "https://x", "dialect": "gtfsrt-servicealerts"})

        class _FakeResponse:
            url = "https://x"
            status_code = 200
            headers = {}
            content = b"raw"

            def raise_for_status(self):
                return None

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, *_args, **_kwargs):
                return _FakeResponse()

        class _FakeFeed:
            def ParseFromString(self, _data):
                return None

        with patch("echogtfs.datasources.gtfsrt.httpx.AsyncClient", return_value=_FakeClient()), patch(
            "echogtfs.datasources.gtfsrt.gtfs_realtime_pb2.FeedMessage", return_value=_FakeFeed()
        ), patch("echogtfs.datasources.gtfsrt.MessageToDict", return_value={}), patch(
            "echogtfs.datasources.gtfsrt.GtfsRtServiceAlertsTransformer"
        ) as transformer_cls, patch.object(gtfsrt_module.logger, "error"):
            transformer_cls.return_value.transform.side_effect = RuntimeError("bad-transform")
            with self.assertRaises(ValueError):
                await datasource._fetch_records()