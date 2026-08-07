from __future__ import annotations

import os
import sys
import unittest
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.scheduler.datasource_scheduler_service import DatasourceSchedulerService
from echogtfs.services.scheduler import datasource_scheduler_service as scheduler_module


@dataclass
class _DataSourceStub:
    id: int
    name: str
    type: str = "dummy"
    config: str = "{}"
    cron: str | None = None
    is_active: bool = True
    log_dumps: bool = False


class _FakeScheduler:
    def __init__(self, jobs: list[SimpleNamespace] | None = None):
        self.jobs = {job.id: job for job in jobs or []}
        self.removed_job_ids: list[str] = []
        self.added_jobs: list[dict[str, object]] = []

    def get_jobs(self) -> list[SimpleNamespace]:
        return list(self.jobs.values())

    def get_job(self, job_id: str) -> SimpleNamespace | None:
        return self.jobs.get(job_id)

    def remove_job(self, job_id: str) -> None:
        self.removed_job_ids.append(job_id)
        self.jobs.pop(job_id, None)

    def add_job(self, func, trigger, args, id, replace_existing) -> None:
        self.added_jobs.append(
            {
                "func": func,
                "trigger": trigger,
                "args": args,
                "id": id,
                "replace_existing": replace_existing,
            }
        )
        self.jobs[id] = SimpleNamespace(id=id)


class _RepositoryStub:
    def __init__(self):
        self.list_active_data_sources_with_cron = AsyncMock(return_value=[])
        self.get_data_source_by_id = AsyncMock(return_value=None)
        self.update_data_source_last_run_at = AsyncMock(return_value=True)
        self.session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    @asynccontextmanager
    async def get_session(self):
        yield self.session


class TestDatasourceSchedulerService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        DatasourceSchedulerService._instance = None
        DatasourceSchedulerService._scheduler = None

    def tearDown(self):
        DatasourceSchedulerService._instance = None
        DatasourceSchedulerService._scheduler = None

    async def test_schedule_all_data_sources_replaces_existing_alert_jobs(self):
        repository = _RepositoryStub()
        realtime_repository = SimpleNamespace()
        gtfs_repository = SimpleNamespace()
        repository.list_active_data_sources_with_cron.return_value = [
            _DataSourceStub(id=1, name="Alpha", cron="*/5 * * * *"),
            _DataSourceStub(id=2, name="Beta", cron="0 * * * *"),
        ]
        scheduler = _FakeScheduler([SimpleNamespace(id="alert_import_9"), SimpleNamespace(id="other_job")])
        DatasourceSchedulerService._scheduler = scheduler

        service = DatasourceSchedulerService(repository, realtime_repository, gtfs_repository)

        await service.schedule_all_data_sources()

        self.assertEqual(scheduler.removed_job_ids, ["alert_import_9"])
        self.assertEqual([job["id"] for job in scheduler.added_jobs], ["alert_import_1", "alert_import_2"])

    async def test_run_import_task_commits_and_updates_last_run_at_on_success(self):
        repository = _RepositoryStub()
        realtime_repository = SimpleNamespace()
        gtfs_repository = SimpleNamespace()
        repository.get_data_source_by_id.return_value = _DataSourceStub(id=7, name="Alpha")
        service = DatasourceSchedulerService(repository, realtime_repository, gtfs_repository)
        datasource = SimpleNamespace(sync_records=AsyncMock(return_value={"added": 1, "updated": 2, "deleted": 3}))

        with patch.object(DatasourceSchedulerService, "_get_datasource", return_value=datasource):
            await service.run_import_task(7)

        datasource.sync_records.assert_awaited_once_with(
            repository,
            realtime_repository,
            gtfs_repository,
            7,
            "Alpha",
            False,
        )
        repository.update_data_source_last_run_at.assert_awaited_once()

    async def test_run_import_task_rolls_back_and_updates_last_run_at_on_error(self):
        repository = _RepositoryStub()
        realtime_repository = SimpleNamespace()
        gtfs_repository = SimpleNamespace()
        repository.get_data_source_by_id.return_value = _DataSourceStub(id=11, name="Broken")
        service = DatasourceSchedulerService(repository, realtime_repository, gtfs_repository)
        datasource = SimpleNamespace(sync_records=AsyncMock(side_effect=RuntimeError("boom")))

        with patch.object(DatasourceSchedulerService, "_get_datasource", return_value=datasource), patch.object(
            scheduler_module.logger,
            "error",
        ):
            await service.run_import_task(11)

        datasource.sync_records.assert_awaited_once_with(
            repository,
            realtime_repository,
            gtfs_repository,
            11,
            "Broken",
            False,
        )
        repository.update_data_source_last_run_at.assert_awaited_once()

    async def test_schedule_data_source_import_uses_timezone_from_environment(self):
        repository = _RepositoryStub()
        realtime_repository = SimpleNamespace()
        gtfs_repository = SimpleNamespace()
        scheduler = _FakeScheduler()
        DatasourceSchedulerService._scheduler = scheduler

        with patch.dict(os.environ, {"TIMEZONE": "Europe/Berlin"}, clear=False):
            service = DatasourceSchedulerService(repository, realtime_repository, gtfs_repository)
            with patch(
                "echogtfs.services.scheduler.datasource_scheduler_service.CronTrigger.from_crontab",
                return_value="trigger",
            ) as from_crontab_mock:
                await service.schedule_data_source_import(1, "Alpha", "*/5 * * * *")

        from_crontab_mock.assert_called_once()
        self.assertEqual(from_crontab_mock.call_args.kwargs["timezone"], ZoneInfo("Europe/Berlin"))