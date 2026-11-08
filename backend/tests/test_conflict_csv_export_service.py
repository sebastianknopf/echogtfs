import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from echogtfs.enum.conflicts import ConflictType
from echogtfs.services.conflict.conflict_csv_export_service import ConflictCsvExportService
from echogtfs.validation.schemas import MonitoringConflictObject, MonitoringDatasourceGroupObject


class TestConflictCsvExportService(unittest.TestCase):

    def test_to_csv_writes_header_and_flat_property_chain(self):
        timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        conflict = MonitoringConflictObject(
            id="abc",
            timestamp=timestamp,
            code=ConflictType.ERROR_NO_STOP_FOUND,
            message=ConflictType.ERROR_NO_STOP_FOUND.name,
            datasource=MonitoringDatasourceGroupObject(id=7, name="ds"),
            properties={"datasource_id": 7, "stop_id": "s1", "last_failure": timestamp},
        )

        service = ConflictCsvExportService(None, None)
        lines = service.to_csv([conflict]).splitlines()

        self.assertEqual(lines[0], "ID;Code;Message;DataSourceID;Properties")
        self.assertEqual(
            lines[1],
            "abc;1003;ERROR_NO_STOP_FOUND;7;datasource_id;7;stop_id;s1;last_failure;2026-01-02T03:04:05+00:00",
        )


class TestConflictCsvExportFiltering(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        datasource = MonitoringDatasourceGroupObject(id=7, name="ds")
        self.conflicts = [
            MonitoringConflictObject(
                id="error",
                timestamp=timestamp,
                code=ConflictType.ERROR_NO_STOP_FOUND,
                message=ConflictType.ERROR_NO_STOP_FOUND.name,
                datasource=datasource,
                properties={},
            ),
            MonitoringConflictObject(
                id="warning",
                timestamp=timestamp,
                code=ConflictType.WARNING_WRONG_QUAY,
                message=ConflictType.WARNING_WRONG_QUAY.name,
                datasource=datasource,
                properties={},
            ),
        ]
        self.service = ConflictCsvExportService(None, None)
        self.service.export = AsyncMock(return_value=self.conflicts)

    async def test_export_filters_by_conflict_code_or_message(self):
        code_csv = await self.service.export_csv(filter_messages_or_codes=["1003"])
        message_csv = await self.service.export_csv(
            filter_messages_or_codes=[ConflictType.WARNING_WRONG_QUAY.name]
        )

        self.assertIn("error;1003;ERROR_NO_STOP_FOUND;7", code_csv)
        self.assertNotIn("warning;2003;WARNING_WRONG_QUAY;7", code_csv)
        self.assertIn("warning;2003;WARNING_WRONG_QUAY;7", message_csv)
        self.assertNotIn("error;1003;ERROR_NO_STOP_FOUND;7", message_csv)

    async def test_empty_or_missing_filter_exports_all_conflicts(self):
        for filters in (None, []):
            with self.subTest(filters=filters):
                csv_content = await self.service.export_csv(filter_messages_or_codes=filters)
                self.assertIn("error;1003;ERROR_NO_STOP_FOUND;7", csv_content)
                self.assertIn("warning;2003;WARNING_WRONG_QUAY;7", csv_content)


if __name__ == "__main__":
    unittest.main()
