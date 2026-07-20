from __future__ import annotations

import json
import time

from google.protobuf.json_format import MessageToDict

from echogtfs import gtfs_realtime_pb2
from echogtfs.enum.gtfsrt import PeriodType
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.database.models import ServiceAlert
from echogtfs.services.gtfsrt.intf_gtfs_realtime_export import GtfsRealtimeExportInterface


class GtfsRealtimeServiceAlertsExportService(GtfsRealtimeExportInterface):
    """GTFS-Realtime export service for ServiceAlert objects."""

    def __init__(self, repository: SystemRepositoryInterface):
        self._repository = repository

    async def export_protobuf(self) -> bytes:
        """Export active ServiceAlerts as GTFS-RT protobuf payload."""
        alerts = await self._load_alerts()
        feed = self._build_feed_message(alerts)

        return feed.SerializeToString()

    async def export_json(self) -> bytes:
        """Export active ServiceAlerts as GTFS-RT JSON payload."""
        alerts = await self._load_alerts()
        feed = self._build_feed_message(alerts)
        feed_dict = MessageToDict(
            feed,
            preserving_proto_field_name=True,
            use_integers_for_enums=False,
        )
        
        return json.dumps(feed_dict, indent=2).encode("utf-8")

    async def _load_alerts(self) -> list[ServiceAlert]:
        """Load active ServiceAlert entities with inflated relationships."""
        return list(await self._repository.get_realtime_service_alerts())

    def _build_feed_message(self, alerts: list[ServiceAlert]) -> gtfs_realtime_pb2.FeedMessage:
        """Build GTFS-RT FeedMessage from ServiceAlert models."""
        feed = gtfs_realtime_pb2.FeedMessage()

        feed.header.gtfs_realtime_version = "2.0"
        feed.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET
        feed.header.timestamp = int(time.time())

        for alert_model in alerts:
            entity = feed.entity.add()
            entity.id = str(alert_model.id)

            alert = entity.alert

            if alert_model.cause:
                alert.cause = getattr(
                    gtfs_realtime_pb2.Alert.Cause,
                    alert_model.cause,
                    gtfs_realtime_pb2.Alert.Cause.UNKNOWN_CAUSE,
                )

            if alert_model.effect:
                alert.effect = getattr(
                    gtfs_realtime_pb2.Alert.Effect,
                    alert_model.effect,
                    gtfs_realtime_pb2.Alert.Effect.UNKNOWN_EFFECT,
                )

            if alert_model.severity_level:
                severity_map = {
                    "UNKNOWN_SEVERITY": gtfs_realtime_pb2.Alert.UNKNOWN_SEVERITY,
                    "INFO": gtfs_realtime_pb2.Alert.INFO,
                    "WARNING": gtfs_realtime_pb2.Alert.WARNING,
                    "SEVERE": gtfs_realtime_pb2.Alert.SEVERE,
                }
                alert.severity_level = severity_map.get(
                    alert_model.severity_level,
                    gtfs_realtime_pb2.Alert.UNKNOWN_SEVERITY,
                )

            for trans in alert_model.translations:
                if trans.header_text:
                    header = alert.header_text.translation.add()
                    header.text = trans.header_text
                    header.language = trans.language

                if trans.description_text:
                    desc = alert.description_text.translation.add()
                    desc.text = trans.description_text
                    desc.language = trans.language

                if trans.url:
                    url = alert.url.translation.add()
                    url.text = trans.url
                    url.language = trans.language

            for period in alert_model.active_periods:
                if period.period_type == PeriodType.IMPACT_PERIOD:
                    time_range = alert.active_period.add()
                    if period.start_time is not None:
                        time_range.start = period.start_time
                    if period.end_time is not None:
                        time_range.end = period.end_time

                    impact_range = alert.impact_period.add()
                    if period.start_time is not None:
                        impact_range.start = period.start_time
                    if period.end_time is not None:
                        impact_range.end = period.end_time
                else:
                    comm_range = alert.communication_period.add()
                    if period.start_time is not None:
                        comm_range.start = period.start_time
                    if period.end_time is not None:
                        comm_range.end = period.end_time

            for entity_model in alert_model.informed_entities:
                informed = alert.informed_entity.add()

                if entity_model.agency_id:
                    informed.agency_id = entity_model.agency_id
                if entity_model.route_id:
                    informed.route_id = entity_model.route_id
                if entity_model.route_type is not None:
                    informed.route_type = entity_model.route_type
                if entity_model.stop_id:
                    informed.stop_id = entity_model.stop_id
                if entity_model.direction_id is not None:
                    informed.direction_id = entity_model.direction_id

                if entity_model.trip_id:
                    informed.trip.trip_id = entity_model.trip_id

        return feed

