from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

fake_config = types.ModuleType("echogtfs.common.config")
fake_config.settings = SimpleNamespace(
    secret_key="test-secret",
    global_id_pattern=None,
    database_url="sqlite+aiosqlite://",
    redis_url="redis://localhost:6379/0",
    debug=False,
)
fake_config.Settings = object
sys.modules.setdefault("echogtfs.common.config", fake_config)

from fastapi import HTTPException

from echogtfs.routers import sources
from echogtfs.validation.schemas import DataSourceUpdate


def _source(*, source_id: int, is_active: bool) -> SimpleNamespace:
    return SimpleNamespace(
        id=source_id,
        name="Alpha",
        type="dummy",
        config="{}",
        execution_type="time_based",
        is_active=is_active,
        cron="*/5 * * * *",
    )


class TestSourcesRouterDeactivation(unittest.IsolatedAsyncioTestCase):
    async def _collect_stream_text(self, response) -> str:
        chunks: list[str] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode("utf-8"))
        return "".join(chunks)

    async def test_toggle_source_active_waits_for_idle_then_deletes(self):
        source_before = _source(source_id=5, is_active=True)
        source_after = _source(source_id=5, is_active=False)
        repository = SimpleNamespace(
            get_data_source_by_id=AsyncMock(side_effect=[source_before, source_before]),
            toggle_data_source_active=AsyncMock(return_value=source_after),
        )
        realtime_repository = SimpleNamespace(
            delete_alerts_for_data_source=AsyncMock(return_value=3),
            delete_trips_for_data_source=AsyncMock(return_value=2),
            delete_vehicles_for_data_source=AsyncMock(return_value=1),
        )
        scheduler = SimpleNamespace(
            schedule_data_source_import=AsyncMock(),
            wait_for_source_idle=AsyncMock(return_value=True),
        )

        with patch("echogtfs.routers.sources.get_datasource_scheduler_service", return_value=scheduler):
            response = await sources.toggle_source_active(5, None, repository, realtime_repository)
            body_text = await self._collect_stream_text(response)

        self.assertIn("intf.sources.toggle.running", body_text)
        self.assertIn("intf.sources.toggle.waiting", body_text)
        self.assertIn("sources.deactivated", body_text)
        scheduler.schedule_data_source_import.assert_awaited_once_with(5, "Alpha", None)
        scheduler.wait_for_source_idle.assert_awaited_once_with(5, timeout_seconds=300.0)
        realtime_repository.delete_alerts_for_data_source.assert_awaited_once_with(5)
        realtime_repository.delete_trips_for_data_source.assert_awaited_once_with(5)
        realtime_repository.delete_vehicles_for_data_source.assert_awaited_once_with(5)

    async def test_toggle_source_active_streams_timeout_when_wait_times_out(self):
        source_before = _source(source_id=5, is_active=True)
        source_after = _source(source_id=5, is_active=False)
        repository = SimpleNamespace(
            get_data_source_by_id=AsyncMock(side_effect=[source_before, source_before]),
            toggle_data_source_active=AsyncMock(return_value=source_after),
        )
        realtime_repository = SimpleNamespace(
            delete_alerts_for_data_source=AsyncMock(),
            delete_trips_for_data_source=AsyncMock(),
            delete_vehicles_for_data_source=AsyncMock(),
        )
        scheduler = SimpleNamespace(
            schedule_data_source_import=AsyncMock(),
            wait_for_source_idle=AsyncMock(return_value=False),
        )

        with patch("echogtfs.routers.sources.get_datasource_scheduler_service", return_value=scheduler):
            response = await sources.toggle_source_active(5, None, repository, realtime_repository)
            body_text = await self._collect_stream_text(response)

        self.assertIn("intf.sources.toggle.timeout", body_text)
        realtime_repository.delete_alerts_for_data_source.assert_not_awaited()
        realtime_repository.delete_trips_for_data_source.assert_not_awaited()
        realtime_repository.delete_vehicles_for_data_source.assert_not_awaited()

    async def test_toggle_source_deactivates_when_subscription_stop_fails(self):
        source_before = _source(source_id=5, is_active=True)
        source_before.execution_type = "subscription_based"
        source_after = _source(source_id=5, is_active=False)
        source_after.execution_type = "subscription_based"
        repository = SimpleNamespace(
            get_data_source_by_id=AsyncMock(side_effect=[source_before, source_before]),
            toggle_data_source_active=AsyncMock(return_value=source_after),
        )
        realtime_repository = SimpleNamespace(
            delete_alerts_for_data_source=AsyncMock(return_value=3),
            delete_trips_for_data_source=AsyncMock(return_value=2),
            delete_vehicles_for_data_source=AsyncMock(return_value=1),
        )
        scheduler = SimpleNamespace(
            schedule_data_source_import=AsyncMock(),
            wait_for_source_idle=AsyncMock(return_value=True),
        )
        subscription_service = SimpleNamespace(stop_subscription=AsyncMock(return_value=False))

        with patch(
            "echogtfs.routers.sources._get_subscription_datasource",
            return_value=SimpleNamespace(),
        ), patch(
            "echogtfs.routers.sources.get_siri_subscription_service",
            return_value=subscription_service,
        ), patch("echogtfs.routers.sources.get_datasource_scheduler_service", return_value=scheduler), self.assertLogs(
            "uvicorn",
            level="ERROR",
        ):
            response = await sources.toggle_source_active(5, None, repository, realtime_repository)
            body_text = await self._collect_stream_text(response)

        self.assertIn("sources.deactivated", body_text)
        repository.toggle_data_source_active.assert_awaited_once_with(5)
        subscription_service.stop_subscription.assert_awaited_once_with(5)
        realtime_repository.delete_alerts_for_data_source.assert_awaited_once_with(5)
        realtime_repository.delete_trips_for_data_source.assert_awaited_once_with(5)
        realtime_repository.delete_vehicles_for_data_source.assert_awaited_once_with(5)

    async def test_toggle_source_activates_when_subscription_start_fails(self):
        source_before = _source(source_id=6, is_active=False)
        source_before.execution_type = "subscription_based"
        source_after = _source(source_id=6, is_active=True)
        source_after.execution_type = "subscription_based"
        repository = SimpleNamespace(
            get_data_source_by_id=AsyncMock(side_effect=[source_before, source_before]),
            toggle_data_source_active=AsyncMock(return_value=source_after),
        )
        realtime_repository = SimpleNamespace()
        scheduler = SimpleNamespace(schedule_data_source_import=AsyncMock())
        subscription_service = SimpleNamespace(start_subscription=AsyncMock(return_value=False))

        with patch(
            "echogtfs.routers.sources._get_subscription_datasource",
            return_value=SimpleNamespace(get_subscription_params=lambda: {}),
        ), patch(
            "echogtfs.routers.sources.get_siri_subscription_service",
            return_value=subscription_service,
        ), patch("echogtfs.routers.sources.get_datasource_scheduler_service", return_value=scheduler), self.assertLogs(
            "uvicorn",
            level="ERROR",
        ):
            response = await sources.toggle_source_active(6, None, repository, realtime_repository)
            body_text = await self._collect_stream_text(response)

        self.assertIn("sources.activated", body_text)
        repository.toggle_data_source_active.assert_awaited_once_with(6)
        subscription_service.start_subscription.assert_awaited_once_with(6, {})
        scheduler.schedule_data_source_import.assert_awaited_once_with(6, "Alpha", "*/5 * * * *")

    async def test_update_source_deactivation_waits_then_deletes(self):
        source_before = _source(source_id=7, is_active=True)
        source_after = _source(source_id=7, is_active=False)
        repository = SimpleNamespace(
            get_data_source_by_id=AsyncMock(return_value=source_before),
            update_data_source=AsyncMock(return_value=source_after),
        )
        realtime_repository = SimpleNamespace(
            update_service_alert_source_name=AsyncMock(),
            delete_alerts_for_data_source=AsyncMock(return_value=4),
            delete_trips_for_data_source=AsyncMock(return_value=5),
            delete_vehicles_for_data_source=AsyncMock(return_value=6),
        )
        scheduler = SimpleNamespace(
            schedule_data_source_import=AsyncMock(),
            wait_for_source_idle=AsyncMock(return_value=True),
        )

        with patch("echogtfs.routers.sources.get_datasource_scheduler_service", return_value=scheduler), patch(
            "echogtfs.routers.sources._enrich_source_with_error_flag",
            AsyncMock(return_value={"updated": True}),
        ):
            result = await sources.update_source(
                7,
                DataSourceUpdate(is_active=False),
                None,
                repository,
                realtime_repository,
            )

        self.assertEqual(result, {"updated": True})
        scheduler.schedule_data_source_import.assert_awaited_once_with(7, "Alpha", None)
        scheduler.wait_for_source_idle.assert_awaited_once_with(7, timeout_seconds=300.0)
        realtime_repository.delete_alerts_for_data_source.assert_awaited_once_with(7)
        realtime_repository.delete_trips_for_data_source.assert_awaited_once_with(7)
        realtime_repository.delete_vehicles_for_data_source.assert_awaited_once_with(7)

    async def test_update_source_deactivation_returns_409_on_timeout(self):
        source_before = _source(source_id=7, is_active=True)
        source_after = _source(source_id=7, is_active=False)
        repository = SimpleNamespace(
            get_data_source_by_id=AsyncMock(return_value=source_before),
            update_data_source=AsyncMock(return_value=source_after),
        )
        realtime_repository = SimpleNamespace(
            update_service_alert_source_name=AsyncMock(),
            delete_alerts_for_data_source=AsyncMock(),
            delete_trips_for_data_source=AsyncMock(),
            delete_vehicles_for_data_source=AsyncMock(),
        )
        scheduler = SimpleNamespace(
            schedule_data_source_import=AsyncMock(),
            wait_for_source_idle=AsyncMock(return_value=False),
        )

        with patch("echogtfs.routers.sources.get_datasource_scheduler_service", return_value=scheduler):
            with self.assertRaises(HTTPException) as ctx:
                await sources.update_source(
                    7,
                    DataSourceUpdate(is_active=False),
                    None,
                    repository,
                    realtime_repository,
                )

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, "error.source_still_running")
        realtime_repository.delete_alerts_for_data_source.assert_not_awaited()
        realtime_repository.delete_trips_for_data_source.assert_not_awaited()
        realtime_repository.delete_vehicles_for_data_source.assert_not_awaited()

    async def test_update_source_does_not_mutate_when_subscription_stop_fails(self):
        source_before = _source(source_id=7, is_active=True)
        source_before.execution_type = "subscription_based"
        repository = SimpleNamespace(
            get_data_source_by_id=AsyncMock(return_value=source_before),
            data_source_name_exists=AsyncMock(return_value=False),
            update_data_source=AsyncMock(),
        )
        realtime_repository = SimpleNamespace(
            update_service_alert_source_name=AsyncMock(),
        )
        stop_error = HTTPException(status_code=502, detail="subscription stop failed")

        with patch("echogtfs.routers.sources._stop_source_subscription", AsyncMock(side_effect=stop_error)):
            with self.assertRaises(HTTPException) as ctx:
                await sources.update_source(
                    7,
                    DataSourceUpdate(name="Renamed"),
                    None,
                    repository,
                    realtime_repository,
                )

        self.assertIs(ctx.exception, stop_error)
        realtime_repository.update_service_alert_source_name.assert_not_awaited()
        repository.update_data_source.assert_not_awaited()


class TestSourcesRouterDelete(unittest.IsolatedAsyncioTestCase):
    async def _delete_source_with_stop_result(self, stop_subscription: AsyncMock):
        source = _source(source_id=9, is_active=True)
        source.execution_type = "subscription_based"
        repository = SimpleNamespace(
            get_data_source_by_id=AsyncMock(return_value=source),
            delete_data_source=AsyncMock(),
        )
        datalog_service = SimpleNamespace(delete_logs_for_data_source=AsyncMock())
        scheduler = SimpleNamespace(schedule_data_source_import=AsyncMock())
        subscription_service = SimpleNamespace(stop_subscription=stop_subscription)

        with patch("echogtfs.routers.sources.DatalogService", return_value=datalog_service), patch(
            "echogtfs.routers.sources.get_datasource_scheduler_service",
            return_value=scheduler,
        ), patch(
            "echogtfs.routers.sources.get_siri_subscription_service",
            return_value=subscription_service,
        ):
            await sources.delete_source(9, None, repository)

        return repository, datalog_service, scheduler

    async def test_delete_source_continues_when_subscription_stop_returns_false(self):
        stop_subscription = AsyncMock(return_value=False)

        repository, datalog_service, scheduler = await self._delete_source_with_stop_result(stop_subscription)

        stop_subscription.assert_awaited_once_with(9)
        datalog_service.delete_logs_for_data_source.assert_awaited_once_with(9)
        scheduler.schedule_data_source_import.assert_awaited_once_with(9, "Alpha", None)
        repository.delete_data_source.assert_awaited_once_with(9)

    async def test_delete_source_continues_when_subscription_stop_raises(self):
        stop_subscription = AsyncMock(side_effect=RuntimeError("consumer unavailable"))

        with self.assertLogs("uvicorn", level="ERROR"):
            repository, datalog_service, scheduler = await self._delete_source_with_stop_result(stop_subscription)

        stop_subscription.assert_awaited_once_with(9)
        datalog_service.delete_logs_for_data_source.assert_awaited_once_with(9)
        scheduler.schedule_data_source_import.assert_awaited_once_with(9, "Alpha", None)
        repository.delete_data_source.assert_awaited_once_with(9)


if __name__ == "__main__":
    unittest.main()
