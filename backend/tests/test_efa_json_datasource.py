from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _service_test_bootstrap  # noqa: F401

from echogtfs.datasources import DATASOURCE_REGISTRY
from echogtfs.datasources import efa_json as efa_json_module
from echogtfs.datasources.transformers import efa_json_service_alerts_transformer as transformer_module
from echogtfs.datasources.efa_json import EfaJsonDatasource



def _silence_logs(test_case, *modules):
    for module in modules:
        for level in ("debug", "info", "warning", "error", "exception"):
            patcher = patch.object(module.logger, level)
            patcher.start()
            test_case.addCleanup(patcher.stop)


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _info(producer: str = "NVBW", message_ref: str = "5344136a-6e54-550e-9310-77998a004199") -> dict:
    return {
        "type": "lineInfo",
        "id": "ems-11863",
        "priority": "high",
        "timestamps": {
            "availability": {"from": _iso(timedelta(days=-1)), "to": _iso(timedelta(days=1))},
        },
        "infoLinks": [
            {"url": "http://nohost", "subtitle": "Sperrung", "content": "Text<br>H&auml;"}
        ],
        "properties": {"producerRef": producer, "messageRef": message_ref, "providerCode": "bodo"},
        "affected": {"lines": [{"id": "bod:05020: :R:"}]},
    }


def _payload(*infos: dict) -> str:
    return json.dumps({"infos": {"current": list(infos)}})


def _config(**overrides) -> dict:
    config = {
        "endpoint": "https://example.com/efa.json",
        "dialect": "ADDINFO",
        "language": "DE",
        "_source_name": "efa-src",
    }
    config.update(overrides)
    return config


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code
        self.url = "https://example.com/efa.json"
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("GET", self.url), response=httpx.Response(self.status_code)
            )


class _FakeClient:
    calls: list = []
    response: _FakeResponse | Exception = _FakeResponse("{}")

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        _FakeClient.calls.append((url, headers))
        if isinstance(_FakeClient.response, Exception):
            raise _FakeClient.response
        return _FakeClient.response


def _fake_http(response):
    _FakeClient.calls = []
    _FakeClient.response = response
    return patch("echogtfs.datasources.efa_json.httpx.AsyncClient", _FakeClient)


class TestEfaJsonDatasourceConfig(unittest.TestCase):
    def setUp(self):
        _silence_logs(self, efa_json_module, transformer_module)

    def test_valid_config(self):
        datasource = EfaJsonDatasource(_config())

        self.assertEqual(datasource.get_datasource_type(), "efa-json")

    def test_registered(self):
        self.assertIs(DATASOURCE_REGISTRY["efa-json"], EfaJsonDatasource)

    def test_schema_fields(self):
        schema = {field["name"]: field for field in EfaJsonDatasource.get_config_schema()}

        self.assertEqual([*schema][-4:], ["endpoint", "dialect", "language", "filter"])
        self.assertEqual(schema["dialect"]["options"], ["ADDINFO"])
        self.assertEqual(schema["language"]["options"], ["DE", "EN"])
        self.assertFalse(schema["filter"]["required"])

    def test_missing_endpoint_is_rejected(self):
        for endpoint in (None, "", 5, ["x"]):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    EfaJsonDatasource(_config(endpoint=endpoint))

    def test_endpoint_is_optional_for_event_based_execution(self):
        EfaJsonDatasource(_config(endpoint=None, _execution_type="event_based"))

    def test_invalid_dialect_is_rejected(self):
        for dialect in ("addinfo", "sirisx", "", None, 3):
            with self.subTest(dialect=dialect):
                with self.assertRaises(ValueError):
                    EfaJsonDatasource(_config(dialect=dialect))

    def test_missing_dialect_is_rejected(self):
        config = _config()
        config.pop("dialect")

        with self.assertRaises(ValueError):
            EfaJsonDatasource(config)

    def test_invalid_language_is_rejected(self):
        for language in ("de-DE", "en-GB", "de", "FR", "", None):
            with self.subTest(language=language):
                with self.assertRaises(ValueError):
                    EfaJsonDatasource(_config(language=language))

    def test_missing_language_is_rejected(self):
        config = _config()
        config.pop("language")

        with self.assertRaises(ValueError):
            EfaJsonDatasource(config)

    def test_non_string_filter_is_rejected(self):
        for value in (["NVBW"], 5, {"a": 1}):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    EfaJsonDatasource(_config(filter=value))

    def test_filter_parsing(self):
        filters = EfaJsonDatasource(_config(filter="line/L1 operator/NVBW foo")).get_filters()

        self.assertEqual(filters["line"], ["L1"])
        self.assertEqual(filters["operator"], ["NVBW"])
        self.assertEqual(filters["legacy"], ["foo"])


class TestEfaJsonDatasourceFetch(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _silence_logs(self, efa_json_module, transformer_module)

    async def test_fetch_records_transforms_payload(self):
        datasource = EfaJsonDatasource(_config())

        with _fake_http(_FakeResponse(_payload(_info()))):
            result = await datasource._fetch_records()

        self.assertEqual(result["record_type"], "service_alerts")
        self.assertEqual(len(result["records"]), 1)
        self.assertIn("_transform_runtime_ms", result)
        record = result["records"][0]
        self.assertEqual(record["translations"][0]["language"], "DE")
        self.assertIsNone(record["translations"][0]["url"])

    async def test_fetch_sends_browser_user_agent_and_json_accept(self):
        datasource = EfaJsonDatasource(_config())

        with _fake_http(_FakeResponse(_payload())):
            await datasource._fetch_records()

        url, headers = _FakeClient.calls[0]
        self.assertEqual(url, "https://example.com/efa.json")
        self.assertIn("Firefox", headers["User-Agent"])
        self.assertEqual(headers["Accept"], "application/json")

    async def test_language_is_handed_to_transformer(self):
        datasource = EfaJsonDatasource(_config(language="EN"))

        with _fake_http(_FakeResponse(_payload(_info()))):
            result = await datasource._fetch_records()

        self.assertEqual(result["records"][0]["translations"][0]["language"], "EN")

    async def test_filter_is_applied(self):
        payload = _payload(_info("NVBW", "a"), _info("OTHER", "b"))

        with _fake_http(_FakeResponse(payload)):
            kept = await EfaJsonDatasource(_config(filter="operator/NVBW"))._fetch_records()
            none = await EfaJsonDatasource(_config(filter="operator/NOPE"))._fetch_records()
            by_line = await EfaJsonDatasource(_config(filter="line/bod:*"))._fetch_records()

        self.assertEqual(len(kept["records"]), 1)
        self.assertEqual(none["records"], [])
        self.assertEqual(len(by_line["records"]), 2)

    async def test_empty_feed_yields_no_records(self):
        with _fake_http(_FakeResponse(json.dumps({"infos": {"current": []}}))):
            result = await EfaJsonDatasource(_config())._fetch_records()

        self.assertEqual(result["records"], [])

    async def test_http_errors_raise_value_error(self):
        datasource = EfaJsonDatasource(_config())
        failures = [
            _FakeResponse("boom", 502),
            _FakeResponse("nope", 404),
            httpx.ConnectError("down"),
            httpx.ReadTimeout("slow"),
        ]
        for failure in failures:
            with self.subTest(failure=repr(failure)):
                with _fake_http(failure), self.assertRaisesRegex(ValueError, "Failed to fetch"):
                    await datasource._fetch_records()

    async def test_invalid_json_raises_value_error(self):
        for text in ("", "not json", "{", "<xml/>"):
            with self.subTest(text=text):
                with _fake_http(_FakeResponse(text)), self.assertRaisesRegex(ValueError, "parse"):
                    await EfaJsonDatasource(_config())._fetch_records()

    async def test_invalid_structure_raises_value_error(self):
        for text in ("[]", "null", '"x"', '{"infos": []}', '{"infos": {"current": {}}}'):
            with self.subTest(text=text):
                with _fake_http(_FakeResponse(text)), self.assertRaises(ValueError):
                    await EfaJsonDatasource(_config())._fetch_records()

    async def test_transformer_failure_raises_value_error(self):
        datasource = EfaJsonDatasource(_config())

        with _fake_http(_FakeResponse(_payload(_info()))), patch(
            "echogtfs.datasources.efa_json.EfaJsonServiceAlertsTransformer"
        ) as transformer_cls:
            transformer_cls.return_value.transform.side_effect = RuntimeError("kaputt")
            with self.assertRaisesRegex(ValueError, "transform"):
                await datasource._fetch_records()

    async def test_payload_path_transforms_bytes(self):
        datasource = EfaJsonDatasource(_config())

        result = await datasource._fetch_records_from_payload(
            _payload(_info()).encode("utf-8"), "application/json"
        )

        self.assertEqual(result["record_type"], "service_alerts")
        self.assertEqual(len(result["records"]), 1)

    async def test_payload_path_rejects_invalid_payloads(self):
        datasource = EfaJsonDatasource(_config())
        for payload in (b"", b"not json", b"\xff\xfe\xfa", b"[]"):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    await datasource._fetch_records_from_payload(payload, None)


if __name__ == "__main__":
    unittest.main()
