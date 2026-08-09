from __future__ import annotations

import os
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")

from echogtfs.datasources import sirivm as sirivm_module
from echogtfs.datasources.sirivm import SiriVmDatasource


class TestSirivmDatasource(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._logger_error_patcher = patch.object(sirivm_module.logger, "error")
        cls._logger_warning_patcher = patch.object(sirivm_module.logger, "warning")
        cls._logger_info_patcher = patch.object(sirivm_module.logger, "info")
        cls._logger_error_patcher.start()
        cls._logger_warning_patcher.start()
        cls._logger_info_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._logger_info_patcher.stop()
        cls._logger_warning_patcher.stop()
        cls._logger_error_patcher.stop()
        super().tearDownClass()

    def test_validate_config_rejects_invalid_method(self):
        with self.assertRaises(ValueError):
            SiriVmDatasource(
                {
                    "endpoint": "https://x/{participantRef}",
                    "participantref": "P1",
                    "method": "invalid",
                    "dialect": "sirivm",
                }
            )

    def test_validate_config_rejects_invalid_dialect(self):
        with self.assertRaises(ValueError):
            SiriVmDatasource(
                {
                    "endpoint": "https://x/{participantRef}",
                    "participantref": "P1",
                    "method": "request/response",
                    "dialect": "invalid",
                }
            )

    def test_validate_config_rejects_non_string_filter(self):
        with self.assertRaises(ValueError):
            SiriVmDatasource(
                {
                    "endpoint": "https://x/{participantRef}",
                    "participantref": "P1",
                    "method": "request/response",
                    "dialect": "sirivm",
                    "filter": 123,
                }
            )

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

    def test_resolve_placeholders_replaces_participantref_case_insensitive(self):
        datasource = SiriVmDatasource(
            {
                "endpoint": "https://x/{participantRef}",
                "participantref": "PARTICIPANT_1",
                "method": "request/response",
                "dialect": "sirivm",
            }
        )

        resolved = datasource._resolve_placeholders(
            "https://service/{participantref}/vm/{PARTICIPANTREF}"
        )

        self.assertEqual(
            resolved,
            "https://service/PARTICIPANT_1/vm/PARTICIPANT_1",
        )

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

    async def test_fetch_and_parse_xml_posts_request_and_parses_response(self):
        datasource = SiriVmDatasource(
            {
                "endpoint": "https://x/{participantRef}/vm",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "sirivm",
            }
        )

        response = Mock()
        response.text = "<Root><ok /></Root>"
        response.headers = {"content-type": "application/xml"}
        response.status_code = 200
        response.raise_for_status = Mock()

        with patch("echogtfs.datasources.sirivm.httpx.AsyncClient") as client_cls, patch.object(
            datasource,
            "_run_cpu_bound",
            AsyncMock(return_value=ET.fromstring("<Root><ok /></Root>")),
        ) as run_cpu_bound, patch.object(datasource, "_log_request", AsyncMock()) as log_request:
            client = AsyncMock()
            client.post = AsyncMock(return_value=response)
            client_cls.return_value.__aenter__.return_value = client

            result = await datasource._fetch_and_parse_xml()

        self.assertEqual(result.tag, "Root")
        client.post.assert_awaited_once()
        post_call_args = client.post.await_args.args
        post_call_kwargs = client.post.await_args.kwargs
        self.assertEqual(post_call_args[0], "https://x/P1/vm")
        self.assertEqual(post_call_kwargs["headers"], {"Content-Type": "application/xml; charset=utf-8"})
        self.assertEqual(post_call_kwargs["content"], datasource._build_request_xml())
        run_cpu_bound.assert_awaited_once()
        self.assertEqual(log_request.await_count, 1)

    async def test_fetch_and_parse_xml_raises_on_http_error_and_logs_request(self):
        datasource = SiriVmDatasource(
            {
                "endpoint": "https://x/{participantRef}/vm",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "sirivm",
            }
        )

        response = Mock()
        response.text = "failure"
        response.headers = {"content-type": "text/plain"}
        response.status_code = 503
        response.raise_for_status = Mock(side_effect=httpx.HTTPError("upstream down"))

        with patch("echogtfs.datasources.sirivm.httpx.AsyncClient") as client_cls, patch.object(
            datasource,
            "_log_request",
            AsyncMock(),
        ) as log_request:
            client = AsyncMock()
            client.post = AsyncMock(return_value=response)
            client_cls.return_value.__aenter__.return_value = client

            with self.assertRaises(ValueError):
                await datasource._fetch_and_parse_xml()

        self.assertEqual(log_request.await_count, 1)
        log_kwargs = log_request.await_args.kwargs
        self.assertEqual(log_kwargs["response_status_code"], 503)
        self.assertEqual(log_kwargs["response_content_type"], "text/plain")

    async def test_fetch_and_parse_xml_raises_on_xml_parse_error_and_logs_both_attempts(self):
        datasource = SiriVmDatasource(
            {
                "endpoint": "https://x/{participantRef}/vm",
                "participantref": "P1",
                "method": "request/response",
                "dialect": "sirivm",
            }
        )

        response = Mock()
        response.text = "<broken"
        response.headers = {"content-type": "application/xml"}
        response.status_code = 200
        response.raise_for_status = Mock()

        with patch("echogtfs.datasources.sirivm.httpx.AsyncClient") as client_cls, patch.object(
            datasource,
            "_run_cpu_bound",
            AsyncMock(side_effect=ET.ParseError("invalid xml")),
        ), patch.object(datasource, "_log_request", AsyncMock()) as log_request:
            client = AsyncMock()
            client.post = AsyncMock(return_value=response)
            client_cls.return_value.__aenter__.return_value = client

            with self.assertRaises(ValueError):
                await datasource._fetch_and_parse_xml()

        self.assertEqual(log_request.await_count, 2)
        first_log = log_request.await_args_list[0].kwargs
        second_log = log_request.await_args_list[1].kwargs
        self.assertEqual(first_log["response_content_type"], "application/xml")
        self.assertEqual(second_log["response_status_code"], 500)
        self.assertEqual(second_log["response_content_type"], "text/plain")
