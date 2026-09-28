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
    return SimpleNamespace(id=source_id, name="Alpha", is_active=is_active, cron="*/5 * * * *")


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


if __name__ == "__main__":
    unittest.main()
