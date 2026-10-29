from __future__ import annotations

import logging
from typing import Any

import httpx

from echogtfs.services.subscription.intf_siri_subscription_service import SiriSubscriptionServiceInterface

logger = logging.getLogger("uvicorn")


class SiriSubscriptionService(SiriSubscriptionServiceInterface):
    """Synchronous-as-awaited client for the SIRI consumer subscription API."""

    _SIRI_CONSUMER_BASE_URL = "http://siricomservice:8080"
    _SIRI_CONSUMER_API_URL = f"{_SIRI_CONSUMER_BASE_URL}/api"

    async def _is_service_healthy(self, endpoint: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
                response = await client.get(f"{self._SIRI_CONSUMER_BASE_URL}/health/{endpoint}")
        except httpx.HTTPError as exc:
            logger.warning("[SiriSubscription] Service health check failed: %s", exc)
            return False

        return response.status_code == httpx.codes.OK

    async def is_subscription_service_running(self) -> bool:
        """Return whether the SIRI communication service is running."""
        return await self._is_service_healthy("live")

    async def is_subscription_service_available(self) -> bool:
        """Return whether the SIRI communication service is ready to accept work."""
        return await self._is_service_healthy("ready")

    def _build_subscription_config(
        self,
        datasource_id: int,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not isinstance(config, dict):
            logger.error("[SiriSubscription] Subscription config must be a dictionary")
            return None

        internal_config = {
            "subscription_ref": str(datasource_id),
            "sink": {
                "type": "http",
                "url": f"http://backend:8000/internal/execute/datasource/{datasource_id}",
                "max_concurrency": 1,
            },
        }

        return {**config, **internal_config}

    async def start_subscription(
        self,
        datasource_id: int,
        config: dict[str, Any],
    ) -> bool:
        """Create and activate a subscription."""
        subscription_config = self._build_subscription_config(datasource_id, config)
        if subscription_config is None:
            return False

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    f"{self._SIRI_CONSUMER_API_URL}/subscriptions",
                    json=subscription_config,
                )
        except httpx.HTTPError as exc:
            logger.error("[SiriSubscription] Failed to start datasource %s: %s", datasource_id, exc)
            return False

        if response.status_code != httpx.codes.CREATED:
            logger.error(
                "[SiriSubscription] Start for datasource %s returned HTTP %s: %s",
                datasource_id,
                response.status_code,
                response.text,
            )

            return False

        return True

    async def stop_subscription(self, datasource_id: int) -> bool:
        """Force-terminate and remove a subscription without spooling."""
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.delete(
                    f"{self._SIRI_CONSUMER_API_URL}/subscriptions/{datasource_id}?force&spool=false",
                )
        except httpx.HTTPError as exc:
            logger.error("[SiriSubscription] Failed to stop datasource %s: %s", datasource_id, exc)
            return False

        if response.status_code != httpx.codes.NO_CONTENT:
            logger.error(
                "[SiriSubscription] Stop for datasource %s returned HTTP %s: %s",
                datasource_id,
                response.status_code,
                response.text,
            )
            
            return False

        return True

    async def get_subscription_status(self, datasource_id: int) -> bool:
        """Return whether a subscription is currently active."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._SIRI_CONSUMER_API_URL}/subscriptions/{datasource_id}",
                )
        except httpx.HTTPError as exc:
            logger.error("[SiriSubscription] Failed to get status for datasource %s: %s", datasource_id, exc)
            return False

        if response.status_code != httpx.codes.OK:
            logger.error(
                "[SiriSubscription] Status for datasource %s returned HTTP %s: %s",
                datasource_id,
                response.status_code,
                response.text,
            )
            
            return False

        try:
            payload = response.json()
        except ValueError as exc:
            logger.error(
                "[SiriSubscription] Invalid status response for datasource %s: %s",
                datasource_id,
                exc,
            )
            
            return False

        return isinstance(payload, dict) and payload.get("status") == "active"

    async def restart_subscription(
        self,
        datasource_id: int,
        config: dict[str, Any] | None,
    ) -> bool:
        """Restart in place, or recreate when new configuration is supplied."""
        if config:
            if not await self.stop_subscription(datasource_id):
                return False
            
            return await self.start_subscription(datasource_id, config)

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    f"{self._SIRI_CONSUMER_API_URL}/subscriptions/{datasource_id}/restart",
                )
        except httpx.HTTPError as exc:
            logger.error("[SiriSubscription] Failed to restart datasource %s: %s", datasource_id, exc)
            return False

        if response.status_code != httpx.codes.OK:
            logger.error(
                "[SiriSubscription] Restart for datasource %s returned HTTP %s: %s",
                datasource_id,
                response.status_code,
                response.text,
            )
            
            return False

        return True
