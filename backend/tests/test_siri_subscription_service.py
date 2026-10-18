from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _service_test_bootstrap  # noqa: F401

from echogtfs.services.subscription import siri_subscription_service as siri_subscription_service_module
from echogtfs.services.subscription.siri_subscription_service import SiriSubscriptionService


class _AsyncClientContext:
    def __init__(self, client: AsyncMock) -> None:
        self.client = client

    async def __aenter__(self) -> AsyncMock:
        return self.client

    async def __aexit__(self, exc_type, exc_value, traceback) -> bool:
        return False


class TestSiriSubscriptionService(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        for level in ("error", "warning"):
            logger_patcher = patch.object(siri_subscription_service_module.logger, level)
            logger_patcher.start()
            self.addCleanup(logger_patcher.stop)

        self.service = SiriSubscriptionService()
        self.client = AsyncMock()
        self.client_context = _AsyncClientContext(self.client)
        self.client_patcher = patch(
            "echogtfs.services.subscription.siri_subscription_service.httpx.AsyncClient",
            return_value=self.client_context,
        )
        self.client_patcher.start()
        self.addCleanup(self.client_patcher.stop)

    async def test_health_checks_use_live_and_ready_endpoints(self) -> None:
        self.client.get.side_effect = [
            httpx.Response(httpx.codes.OK),
            httpx.Response(httpx.codes.OK),
        ]

        self.assertTrue(await self.service.is_subscription_service_running())
        self.assertTrue(await self.service.is_subscription_service_available())

        self.assertEqual(
            [call.args[0] for call in self.client.get.await_args_list],
            [
                "http://siricomservice:8080/health/live",
                "http://siricomservice:8080/health/ready",
            ],
        )

    async def test_health_check_returns_false_for_non_200_and_http_error(self) -> None:
        self.client.get.side_effect = [
            httpx.Response(httpx.codes.SERVICE_UNAVAILABLE),
            httpx.ConnectError("service unavailable"),
        ]

        self.assertFalse(await self.service.is_subscription_service_running())
        self.assertFalse(await self.service.is_subscription_service_available())

    async def test_start_subscription_merges_internal_config_and_requires_created(self) -> None:
        self.client.post.return_value = httpx.Response(httpx.codes.CREATED)
        config = {
            "provider_url": "https://provider.example/siri",
            "delivery_mode": "other",
            "subscription_ref": "caller-value",
            "sink": {"type": "other"},
        }

        self.assertTrue(await self.service.start_subscription(42, config))

        self.client.post.assert_awaited_once_with(
            "http://siricomservice:8080/api/subscriptions",
            json={
                "provider_url": "https://provider.example/siri",
                "delivery_mode": "direct",
                "subscription_ref": "42",
                "sink": {
                    "type": "http",
                    "url": "http://backend:8000/internal/execute/datasource/42",
                    "max_concurrency": 1,
                },
            },
        )

    async def test_start_subscription_returns_false_for_invalid_config_status_and_http_error(self) -> None:
        self.assertFalse(await self.service.start_subscription(1, None))  # type: ignore[arg-type]
        self.client.post.return_value = httpx.Response(httpx.codes.BAD_REQUEST)
        self.assertFalse(await self.service.start_subscription(1, {}))

        self.client.post.side_effect = httpx.ConnectError("service unavailable")
        self.assertFalse(await self.service.start_subscription(1, {}))

    async def test_stop_subscription_uses_force_without_spooling(self) -> None:
        self.client.delete.return_value = httpx.Response(httpx.codes.NO_CONTENT)

        self.assertTrue(await self.service.stop_subscription(17))

        self.client.delete.assert_awaited_once_with(
            "http://siricomservice:8080/api/subscriptions/17?force&spool=false",
        )

    async def test_stop_subscription_returns_false_on_unexpected_status_or_http_error(self) -> None:
        self.client.delete.return_value = httpx.Response(httpx.codes.NOT_FOUND)
        self.assertFalse(await self.service.stop_subscription(17))

        self.client.delete.side_effect = httpx.ConnectError("service unavailable")
        self.assertFalse(await self.service.stop_subscription(17))

    async def test_get_subscription_status_is_true_only_for_active_subscription(self) -> None:
        self.client.get.side_effect = [
            httpx.Response(httpx.codes.OK, json={"status": "active"}),
            httpx.Response(httpx.codes.OK, json={"status": "inactive"}),
            httpx.Response(httpx.codes.OK, json=[]),
            httpx.Response(httpx.codes.OK, content=b"invalid", headers={"content-type": "application/json"}),
            httpx.Response(httpx.codes.NOT_FOUND),
        ]

        results = [await self.service.get_subscription_status(9) for _ in range(5)]

        self.assertEqual(results, [True, False, False, False, False])

    async def test_get_subscription_status_returns_false_on_http_error(self) -> None:
        self.client.get.side_effect = httpx.ConnectError("service unavailable")

        self.assertFalse(await self.service.get_subscription_status(9))

    async def test_restart_without_config_calls_restart_endpoint(self) -> None:
        self.client.post.return_value = httpx.Response(httpx.codes.OK)

        self.assertTrue(await self.service.restart_subscription(5, None))

        self.client.post.assert_awaited_once_with(
            "http://siricomservice:8080/api/subscriptions/5/restart",
        )

    async def test_restart_without_config_returns_false_on_failure(self) -> None:
        self.client.post.return_value = httpx.Response(httpx.codes.BAD_REQUEST)
        self.assertFalse(await self.service.restart_subscription(5, None))

        self.client.post.side_effect = httpx.ConnectError("service unavailable")
        self.assertFalse(await self.service.restart_subscription(5, None))

    async def test_restart_with_config_stops_then_starts_subscription(self) -> None:
        calls: list[str] = []

        async def stop_subscription(datasource_id: int) -> bool:
            calls.append(f"stop:{datasource_id}")
            return True

        async def start_subscription(datasource_id: int, config: dict) -> bool:
            calls.append(f"start:{datasource_id}:{config['provider_url']}")
            return True

        self.service.stop_subscription = stop_subscription
        self.service.start_subscription = start_subscription

        self.assertTrue(
            await self.service.restart_subscription(
                5,
                {"provider_url": "https://provider.example/siri"},
            )
        )
        self.assertEqual(calls, ["stop:5", "start:5:https://provider.example/siri"])

    async def test_restart_with_config_does_not_start_if_stop_fails(self) -> None:
        self.service.stop_subscription = AsyncMock(return_value=False)
        self.service.start_subscription = AsyncMock(return_value=True)

        self.assertFalse(await self.service.restart_subscription(5, {"provider_url": "https://example.com"}))
        self.service.stop_subscription.assert_awaited_once_with(5)
        self.service.start_subscription.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
