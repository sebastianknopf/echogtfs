from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.enum.system import ExpiredRealtimeObjectPolicy
from echogtfs.services.cleanup.cleanup_service import CleanupService


class TestCleanupService(unittest.IsolatedAsyncioTestCase):
    async def test_handle_expired_alerts_deactivate(self):
        system_repo = SimpleNamespace()
        realtime_repo = SimpleNamespace(
            list_expired_internal_alert_ids=AsyncMock(return_value=["a", "b"]),
            deactivate_service_alerts=AsyncMock(),
            delete_service_alerts_by_ids=AsyncMock(),
        )
        service = CleanupService(system_repo, realtime_repo)

        count = await service._handle_expired_alerts(ExpiredRealtimeObjectPolicy.DEACTIVATE)

        self.assertEqual(count, 2)
        realtime_repo.deactivate_service_alerts.assert_awaited_once_with(["a", "b"])
        realtime_repo.delete_service_alerts_by_ids.assert_not_awaited()

    async def test_delete_old_expired_alerts(self):
        system_repo = SimpleNamespace()
        realtime_repo = SimpleNamespace(
            list_internal_alert_ids_expired_before=AsyncMock(return_value=["x"]),
            delete_service_alerts_by_ids=AsyncMock(),
        )
        service = CleanupService(system_repo, realtime_repo)

        count = await service._delete_old_expired_alerts(3)

        self.assertEqual(count, 1)
        realtime_repo.delete_service_alerts_by_ids.assert_awaited_once_with(["x"])

    async def test_delete_old_expired_alerts_negative_days_returns_zero(self):
        system_repo = SimpleNamespace()
        realtime_repo = SimpleNamespace(
            list_internal_alert_ids_expired_before=AsyncMock(return_value=["x"]),
            delete_service_alerts_by_ids=AsyncMock(),
        )
        service = CleanupService(system_repo, realtime_repo)

        count = await service._delete_old_expired_alerts(-1)

        self.assertEqual(count, 0)
        realtime_repo.list_internal_alert_ids_expired_before.assert_not_awaited()

    async def test_schedule_from_settings_uses_timezone_from_environment(self):
        class _FakeScheduler:
            def __init__(self) -> None:
                self.jobs: dict[str, object] = {}

            def get_job(self, job_id: str) -> object | None:
                return self.jobs.get(job_id)

            def remove_job(self, job_id: str) -> None:
                self.jobs.pop(job_id, None)

            def add_job(self, func, trigger, id, replace_existing) -> None:
                self.jobs[id] = trigger

        system_repo = SimpleNamespace(get_app_setting=AsyncMock(return_value="*/10 * * * *"))
        realtime_repo = SimpleNamespace()
        scheduler = _FakeScheduler()
        CleanupService._scheduler = scheduler

        with patch.dict(os.environ, {"TIMEZONE": "Europe/Berlin"}, clear=False):
            service = CleanupService(system_repo, realtime_repo)
            with patch(
                "echogtfs.services.cleanup.cleanup_service.CronTrigger.from_crontab",
                return_value="trigger",
            ) as from_crontab_mock:
                await service.schedule_from_settings()

        from_crontab_mock.assert_called_once()
        self.assertEqual(from_crontab_mock.call_args.kwargs["timezone"], ZoneInfo("Europe/Berlin"))