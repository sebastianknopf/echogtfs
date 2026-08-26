from __future__ import annotations

import io
import json
import sys
import unittest
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.database.models import AppSetting, DataSource, DataSourceEnrichment, DataSourceMapping, User
from echogtfs.services.systemcopy.systemcopy_service import SystemCopyService


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, *, users=None, sources=None, mappings=None, enrichments=None):
        self.users = users or []
        self.sources = sources or []
        self.mappings = mappings or []
        self.enrichments = enrichments or []

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is User:
            return _FakeResult(self.users)
        if entity is DataSource:
            return _FakeResult(self.sources)
        if entity is DataSourceMapping:
            return _FakeResult(self.mappings)
        if entity is DataSourceEnrichment:
            return _FakeResult(self.enrichments)
        raise AssertionError(f"Unsupported entity in fake session: {entity}")

    def add(self, obj):
        if isinstance(obj, User):
            self.users.append(obj)
        elif isinstance(obj, DataSource):
            self.sources.append(obj)
        elif isinstance(obj, DataSourceMapping):
            self.mappings.append(obj)
        elif isinstance(obj, DataSourceEnrichment):
            self.enrichments.append(obj)
        else:
            raise AssertionError(f"Unsupported add() type: {type(obj)}")


class _FakeRepository:
    def __init__(self, session):
        self._session = session

    def get_session(self):
        session = self._session

        class _Ctx:
            async def __aenter__(self_inner):
                return session

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()


class TestSystemCopyService(unittest.IsolatedAsyncioTestCase):
    def test_serialize_system_settings_includes_trip_update_realtime_data_setting(self):
        service = SystemCopyService()
        setting = AppSetting(
            key=AppSetting.KEY_GTFS_RT_TRIP_UPDATES_EXCLUDE_TRIPS_WITHOUT_REALTIME_DATA,
            value="true",
        )

        rows = service._serialize_app_settings([setting], keys=set(service._SYSTEM_KEYS))

        self.assertEqual(
            rows,
            [
                {
                    "key": AppSetting.KEY_GTFS_RT_TRIP_UPDATES_EXCLUDE_TRIPS_WITHOUT_REALTIME_DATA,
                    "value": "true",
                }
            ],
        )

    def test_serialize_data_sources_resets_last_run_at(self):
        service = SystemCopyService()
        source = DataSource(
            id=1,
            name="source-1",
            type="sirilite",
            config="{}",
            cron="*/10 * * * *",
            is_active=True,
            invalid_reference_policy="not_specified",
            last_run_at=datetime(2026, 8, 3, 10, 0, 0, tzinfo=UTC),
        )

        rows = service._serialize_data_sources([source])
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["last_run_at"])

    async def test_import_users_remaps_id_when_id_exists_but_username_differs(self):
        session = _FakeSession(
            users=[
                User(
                    id=1,
                    username="alice",
                    email="alice@example.com",
                    hashed_password="hash-a",
                    is_active=True,
                    is_superuser=False,
                    is_technical_contact=False,
                )
            ]
        )
        service = SystemCopyService()

        created, updated, remapped = await service._import_users(
            session,
            [
                {
                    "id": 1,
                    "username": "bob",
                    "email": "bob@example.com",
                    "hashed_password": "hash-b",
                    "is_active": True,
                    "is_superuser": True,
                    "is_technical_contact": False,
                }
            ],
        )

        self.assertEqual(created, 1)
        self.assertEqual(updated, 0)
        self.assertEqual(remapped, 1)
        self.assertEqual(len(session.users), 2)
        bob = next(u for u in session.users if u.username == "bob")
        self.assertEqual(bob.id, 2)

    async def test_import_users_updates_by_username(self):
        existing = User(
            id=4,
            username="alice",
            email="alice@example.com",
            hashed_password="old-hash",
            is_active=True,
            is_superuser=False,
            is_technical_contact=False,
        )
        session = _FakeSession(users=[existing])
        service = SystemCopyService()

        created, updated, remapped = await service._import_users(
            session,
            [
                {
                    "id": 99,
                    "username": "alice",
                    "email": "alice-new@example.com",
                    "hashed_password": "new-hash",
                    "is_active": False,
                    "is_superuser": True,
                    "is_technical_contact": True,
                }
            ],
        )

        self.assertEqual(created, 0)
        self.assertEqual(updated, 1)
        self.assertEqual(remapped, 0)
        self.assertEqual(existing.id, 4)
        self.assertEqual(existing.email, "alice-new@example.com")
        self.assertEqual(existing.hashed_password, "new-hash")
        self.assertFalse(existing.is_active)
        self.assertTrue(existing.is_superuser)
        self.assertTrue(existing.is_technical_contact)

    async def test_import_datasources_remaps_id_and_child_rows_follow_mapped_id(self):
        session = _FakeSession(
            sources=[
                DataSource(
                    id=1,
                    name="existing-source",
                    type="sirilite",
                    config="{}",
                    cron=None,
                    is_active=True,
                    invalid_reference_policy="not_specified",
                )
            ],
            mappings=[],
            enrichments=[],
        )
        service = SystemCopyService()

        created, updated, remapped = await service._import_data_sources(
            session,
            source_rows=[
                {
                    "id": 1,
                    "name": "new-source",
                    "type": "sirisx",
                    "config": "{}",
                    "cron": "*/10 * * * *",
                    "is_active": True,
                    "invalid_reference_policy": "not_specified",
                }
            ],
            mapping_rows=[
                {
                    "id": 1,
                    "data_source_id": 1,
                    "entity_type": "route",
                    "key": "EXTERNAL",
                    "value": "R1",
                }
            ],
            enrichment_rows=[
                {
                    "id": 1,
                    "data_source_id": 1,
                    "enrichment_type": "effect",
                    "source_field": "header",
                    "key": "strike",
                    "value": "NO_SERVICE",
                    "sort_order": 0,
                }
            ],
        )

        self.assertEqual(remapped, 1)
        self.assertEqual(created, 3)
        self.assertEqual(updated, 0)
        new_source = next(s for s in session.sources if s.name == "new-source")
        self.assertEqual(new_source.id, 2)
        self.assertEqual(len(session.mappings), 1)
        self.assertEqual(session.mappings[0].data_source_id, 2)
        self.assertEqual(len(session.enrichments), 1)
        self.assertEqual(session.enrichments[0].data_source_id, 2)

    async def test_import_zip_schedules_datasources_when_datasource_file_present(self):
        session = _FakeSession()
        session.commit = AsyncMock()
        session.get = AsyncMock(return_value=None)
        session.get_bind = lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
        repository = _FakeRepository(session)

        service = SystemCopyService(repository)

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "manifest.json",
                json.dumps({"format_version": 1, "selected_domains": {"datasources": True}}).encode("utf-8"),
            )
            zf.writestr("sys_data_sources.json", json.dumps([]).encode("utf-8"))

        scheduler = SimpleNamespace(schedule_all_data_sources=AsyncMock())

        with patch("echogtfs.services.systemcopy.systemcopy_service.get_datasource_scheduler_service", return_value=scheduler), patch.object(
            service,
            "_import_data_sources",
            AsyncMock(return_value=(0, 0, 0)),
        ):
            await service.import_zip(archive.getvalue())

        scheduler.schedule_all_data_sources.assert_awaited_once()
