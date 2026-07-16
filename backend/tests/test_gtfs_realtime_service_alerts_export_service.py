from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.enum.gtfsrt import PeriodType
from echogtfs.services.gtfsrt.gtfs_realtime_service_alerts_export_service import (
    GtfsRealtimeServiceAlertsExportService,
)


class TestGtfsRealtimeServiceAlertsExportService(unittest.IsolatedAsyncioTestCase):
    async def test_export_protobuf_contains_alert(self):
        alert = SimpleNamespace(
            id="abc",
            cause="MAINTENANCE",
            effect="DETOUR",
            severity_level="WARNING",
            translations=[SimpleNamespace(header_text="H", description_text="D", url=None, language="de")],
            active_periods=[SimpleNamespace(period_type=PeriodType.IMPACT_PERIOD, start_time=1, end_time=2)],
            informed_entities=[SimpleNamespace(agency_id="A", route_id="R", route_type=None, stop_id="S", direction_id=None, trip_id=None)],
        )
        repo = SimpleNamespace(get_realtime_service_alerts=AsyncMock(return_value=[alert]))
        service = GtfsRealtimeServiceAlertsExportService(repo)

        fake_feed = SimpleNamespace(SerializeToString=lambda: b"feed-bytes")
        with patch.object(service, "_build_feed_message", return_value=fake_feed) as build_feed:
            payload = await service.export_protobuf()

        self.assertEqual(payload, b"feed-bytes")
        build_feed.assert_called_once()