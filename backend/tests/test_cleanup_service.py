from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.enum.system import ExpiredAlertPolicy
from echogtfs.services.cleanup.cleanup_service import CleanupService


class TestCleanupService(unittest.IsolatedAsyncioTestCase):
    async def test_handle_expired_alerts_deactivate(self):
        repo = SimpleNamespace(
            list_expired_internal_alert_ids=AsyncMock(return_value=["a", "b"]),
            deactivate_service_alerts=AsyncMock(),
            delete_service_alerts_by_ids=AsyncMock(),
        )
        service = CleanupService(repo)

        count = await service._handle_expired_alerts(ExpiredAlertPolicy.DEACTIVATE)

        self.assertEqual(count, 2)
        repo.deactivate_service_alerts.assert_awaited_once_with(["a", "b"])
        repo.delete_service_alerts_by_ids.assert_not_awaited()

    async def test_delete_old_expired_alerts(self):
        repo = SimpleNamespace(
            list_internal_alert_ids_expired_before=AsyncMock(return_value=["x"]),
            delete_service_alerts_by_ids=AsyncMock(),
        )
        service = CleanupService(repo)

        count = await service._delete_old_expired_alerts(3)

        self.assertEqual(count, 1)
        repo.delete_service_alerts_by_ids.assert_awaited_once_with(["x"])

    async def test_delete_old_expired_alerts_negative_days_returns_zero(self):
        repo = SimpleNamespace(
            list_internal_alert_ids_expired_before=AsyncMock(return_value=["x"]),
            delete_service_alerts_by_ids=AsyncMock(),
        )
        service = CleanupService(repo)

        count = await service._delete_old_expired_alerts(-1)

        self.assertEqual(count, 0)
        repo.list_internal_alert_ids_expired_before.assert_not_awaited()