from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs import gtfs_realtime_pb2
from echogtfs.datasources.transformers.gtfsrt_service_alerts_transformer import (
    GtfsRtServiceAlertsTransformer,
)


class TestGtfsRtServiceAlertsTransformer(unittest.TestCase):
    def test_transform_filters_expired_and_maps_payload(self):
        feed = gtfs_realtime_pb2.FeedMessage()

        valid_entity = gtfs_realtime_pb2.FeedEntity()
        feed.entity.append(valid_entity)
        valid_entity.id = "1"
        valid_alert = valid_entity.alert
        valid_alert.cause = gtfs_realtime_pb2.Alert.MAINTENANCE
        valid_alert.effect = gtfs_realtime_pb2.Alert.DETOUR
        valid_alert.severity_level = gtfs_realtime_pb2.Alert.WARNING
        header = gtfs_realtime_pb2.TranslatedString.Translation()
        valid_alert.header_text.translation.append(header)
        header.language = "de-DE"
        header.text = "Header"
        period = gtfs_realtime_pb2.TimeRange()
        valid_alert.active_period.append(period)
        period.start = int(time.time()) - 60
        period.end = int(time.time()) + 3600
        informed = gtfs_realtime_pb2.EntitySelector()
        valid_alert.informed_entity.append(informed)
        informed.route_id = "R1"

        expired_entity = gtfs_realtime_pb2.FeedEntity()
        feed.entity.append(expired_entity)
        expired_entity.id = "2"
        expired_alert = expired_entity.alert
        old_period = gtfs_realtime_pb2.TimeRange()
        expired_alert.active_period.append(old_period)
        old_period.start = int(time.time()) - 7200
        old_period.end = int(time.time()) - 3600

        transformer = GtfsRtServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}"
        )
        records = transformer.transform({"feed": feed, "source_name": "src"})

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "src-1")
        self.assertEqual(records[0]["cause"], "MAINTENANCE")
        self.assertEqual(records[0]["effect"], "DETOUR")
        self.assertEqual(records[0]["severity_level"], "WARNING")

    def test_transform_returns_empty_when_no_alert_entities(self):
        feed = gtfs_realtime_pb2.FeedMessage()
        entity_without_alert = gtfs_realtime_pb2.FeedEntity()
        entity_without_alert.id = "noop"
        feed.entity.append(entity_without_alert)

        transformer = GtfsRtServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}"
        )

        records = transformer.transform({"feed": feed, "source_name": "src"})
        self.assertEqual(records, [])