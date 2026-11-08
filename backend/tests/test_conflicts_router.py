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

from echogtfs.enum.conflicts import ConflictType
from echogtfs.routers.conflicts import export_conflicts_csv, get_conflict_filter_options


class TestConflictsRouter(unittest.IsolatedAsyncioTestCase):
    async def test_export_conflicts_csv_passes_selected_types_to_service(self):
        repository = object()
        realtime_repository = object()

        with patch("echogtfs.routers.conflicts.ConflictCsvExportService") as service_class:
            service = service_class.return_value
            service.export_csv = AsyncMock(return_value="ID;Code;Message;DataSourceID;Properties\r\n")

            response = await export_conflicts_csv(
                None,
                repository,
                realtime_repository,
                12,
                ["1003", "WARNING_WRONG_QUAY"],
            )

        service_class.assert_called_once_with(
            system_repository=repository,
            realtime_repository=realtime_repository,
        )
        service.export_csv.assert_awaited_once_with(
            filter_datasource_id=12,
            filter_messages_or_codes=["1003", "WARNING_WRONG_QUAY"],
        )
        self.assertEqual(response.body, b"ID;Code;Message;DataSourceID;Properties\r\n")

    async def test_get_conflict_filter_options_returns_sources_and_types(self):
        repository = SimpleNamespace(
            list_data_sources=AsyncMock(
                return_value=[
                    SimpleNamespace(id=12, name="City Transit", is_active=True),
                    SimpleNamespace(id=18, name="Regional Transit", is_active=False),
                ]
            )
        )

        response = await get_conflict_filter_options(None, repository)

        self.assertEqual(
            [(source.id, source.name) for source in response.data_sources],
            [(12, "City Transit")],
        )
        self.assertEqual(
            [(conflict_type.code, conflict_type.name) for conflict_type in response.conflict_types],
            [(conflict_type, conflict_type.name) for conflict_type in ConflictType],
        )
        repository.list_data_sources.assert_awaited_once_with()

    async def test_get_conflict_filter_options_excludes_inactive_sources(self):
        repository = SimpleNamespace(
            list_data_sources=AsyncMock(
                return_value=[
                    SimpleNamespace(id=18, name="Regional Transit", is_active=False),
                ]
            )
        )

        response = await get_conflict_filter_options(None, repository)

        self.assertEqual(response.data_sources, [])
        self.assertEqual(len(response.conflict_types), len(ConflictType))

    async def test_get_conflict_filter_options_propagates_repository_error(self):
        repository = SimpleNamespace(
            list_data_sources=AsyncMock(side_effect=RuntimeError("repository unavailable"))
        )

        with self.assertRaisesRegex(RuntimeError, "repository unavailable"):
            await get_conflict_filter_options(None, repository)
