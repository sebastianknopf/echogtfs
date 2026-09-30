from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _service_test_bootstrap  # noqa: F401

from echogtfs.services.realtime_processing.realtime_processing_dispatcher_service import (
    RealtimeProcessingDispatcherService,
)
from _realtime_processing_test_support import (
    _GtfsRepositoryStub,
    _RealtimeRepositoryStub,
    _SystemRepositoryStub,
    make_processor,
)
from echogtfs.services.realtime_processing.service_alert_processing_service import (
    ServiceAlertProcessingService,
)


class TestRealtimeProcessingDispatcherService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        processor = make_processor(ServiceAlertProcessingService)
        self.dispatcher = RealtimeProcessingDispatcherService(
            processor.config,
            processor._entity_enrichment_service,
            processor._identifier_mapping_service,
            processor._caching_service,
        )

    def test_normalize_fetched_payload(self):
        record_type, records = self.dispatcher.normalize_fetched_payload(
            {"record_type": "service_alerts", "records": [{"id": "1"}]}
        )
        self.assertEqual(record_type, "service_alerts")
        self.assertEqual(records, [{"id": "1"}])

    async def test_dispatches_to_matching_processor(self):
        processor = AsyncMock()
        processor.sync_records.return_value = {"added": 1, "updated": 0, "deleted": 0}
        self.dispatcher._processors["service_alerts"] = processor

        result = await self.dispatcher.sync_records(
            "service_alerts",
            [],
            repository=_SystemRepositoryStub(),
            realtime_repository=_RealtimeRepositoryStub(),
            gtfs_repository=_GtfsRepositoryStub(),
            source_id=1,
            source_name="test",
        )

        self.assertEqual(result, {"added": 1, "updated": 0, "deleted": 0})
        processor.sync_records.assert_awaited_once()

    async def test_rejects_unsupported_record_type(self):
        with self.assertRaises(NotImplementedError):
            await self.dispatcher.sync_records(
                "unsupported",
                [],
                repository=_SystemRepositoryStub(),
                realtime_repository=_RealtimeRepositoryStub(),
                gtfs_repository=_GtfsRepositoryStub(),
                source_id=1,
                source_name="test",
            )


if __name__ == "__main__":
    unittest.main()
