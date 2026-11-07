import unittest
from datetime import datetime, timezone

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


if __name__ == "__main__":
    unittest.main()
