from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.protobuf.json_format import MessageToDict

from echogtfs import gtfs_realtime_pb2
from echogtfs.enum.gtfsrt import WheelchairAccessible
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.models import Vehicle
from echogtfs.services.gtfsrt.intf_gtfs_realtime_export import GtfsRealtimeExportInterface


class GtfsRealtimeVehiclePositionsExportService(GtfsRealtimeExportInterface):
    """GTFS-Realtime export service for VehiclePosition objects."""

    def __init__(self, repository: RealtimeRepositoryInterface):
        self._repository = repository
        self._target_timezone = self._resolve_timezone(self._configured_timezone_name())

    async def export_protobuf(self) -> bytes:
        """Export active Vehicle positions as GTFS-RT protobuf payload."""
        vehicles = await self._load_vehicle_positions()
        feed = self._build_feed_message(vehicles)

        return feed.SerializeToString()

    async def export_json(self) -> bytes:
        """Export active Vehicle positions as GTFS-RT JSON payload."""
        vehicles = await self._load_vehicle_positions()
        feed = self._build_feed_message(vehicles)
        feed_dict = MessageToDict(
            feed,
            preserving_proto_field_name=True,
            use_integers_for_enums=False,
        )

        return json.dumps(feed_dict, indent=2).encode("utf-8")

    async def _load_vehicle_positions(self) -> list[Vehicle]:
        """Load active Vehicle entities with their trip relations."""
        return list(await self._repository.get_realtime_vehicles())

    @staticmethod
    def _timestamp_value(value) -> int | None:
        if value is None:
            return None
        if hasattr(value, "timestamp"):
            return int(value.timestamp())
        
        return int(value)

    @staticmethod
    def _stop_sequence_value(value) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _vehicle_stop_status_to_enum(value: object | None) -> int | None:
        if value is None:
            return None

        text = value.value if hasattr(value, "value") else str(value)
        try:
            return gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Value(text)
        except ValueError:
            return None

    @staticmethod
    def _congestion_level_to_enum(value: object | None) -> int | None:
        if value is None:
            return None

        text = value.value if hasattr(value, "value") else str(value)
        try:
            return gtfs_realtime_pb2.VehiclePosition.CongestionLevel.Value(text)
        except ValueError:
            return None

    @staticmethod
    def _wheelchair_accessible_to_enum(value: WheelchairAccessible | str | None) -> int | None:
        if value is None:
            return None

        text = value.value if hasattr(value, "value") else str(value)
        try:
            return gtfs_realtime_pb2.VehicleDescriptor.WheelchairAccessible.Value(text)
        except ValueError:
            return None

    @staticmethod
    def _trip_schedule_relationship_to_enum(value: object | None) -> int | None:
        if value is None:
            return None

        text = value.value if hasattr(value, "value") else str(value)
        try:
            return gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Value(text)
        except ValueError:
            return None

    @staticmethod
    def _configured_timezone_name() -> str:
        try:
            from echogtfs.common.config import settings

            timezone_name = getattr(settings, "timezone", "UTC")
        except Exception:  # noqa: BLE001
            timezone_name = "UTC"

        if not isinstance(timezone_name, str) or not timezone_name.strip():
            return "UTC"

        return timezone_name

    @staticmethod
    def _resolve_timezone(timezone_name: object) -> ZoneInfo:
        if not isinstance(timezone_name, str) or not timezone_name.strip():
            return ZoneInfo("UTC")

        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    def _localize_start_time(self, start_date: str, start_time: str) -> str:
        if not start_date or not start_time:
            return start_time

        date_part = start_date.strip()
        time_part = start_time.strip()

        try:
            service_date = datetime.strptime(date_part, "%Y%m%d").date()
        except ValueError:
            return start_time

        parts = time_part.split(":")
        if len(parts) != 3:
            return start_time

        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
        except ValueError:
            return start_time

        if hours < 0 or minutes < 0 or minutes > 59 or seconds < 0 or seconds > 59:
            return start_time

        source_base = datetime(service_date.year, service_date.month, service_date.day, tzinfo=ZoneInfo("UTC"))
        source_timestamp = source_base + timedelta(hours=hours, minutes=minutes, seconds=seconds)
        local_timestamp = source_timestamp.astimezone(self._target_timezone)
        service_midnight_local = datetime(service_date.year, service_date.month, service_date.day, tzinfo=self._target_timezone)
        total_seconds = int((local_timestamp - service_midnight_local).total_seconds())

        if total_seconds < 0:
            return start_time

        total_hours, remainder = divmod(total_seconds, 3600)
        total_minutes, total_seconds = divmod(remainder, 60)

        return f"{total_hours:02d}:{total_minutes:02d}:{total_seconds:02d}"

    @staticmethod
    def _vehicle_id_value(vehicle_model: Vehicle) -> str:
        return vehicle_model.vehicle_id or str(vehicle_model.id)

    def _build_feed_message(self, vehicles: list[Vehicle]) -> gtfs_realtime_pb2.FeedMessage:
        """Build GTFS-RT FeedMessage from Vehicle models."""
        feed = gtfs_realtime_pb2.FeedMessage()

        feed.header.gtfs_realtime_version = "2.0"
        feed.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET
        feed.header.timestamp = int(time.time())

        for vehicle_model in vehicles:
            entity = feed.entity.add()
            entity.id = str(vehicle_model.id)

            vehicle_position = entity.vehicle
            vehicle_position.timestamp = self._timestamp_value(vehicle_model.timestamp) or int(time.time())
            vehicle_position.current_stop_sequence = self._stop_sequence_value(vehicle_model.current_stop_sequence) or 0

            trip_descriptor = vehicle_position.trip
            trip = vehicle_model.trip
            trip_descriptor.trip_id = trip.trip_id
            trip_descriptor.route_id = trip.route_id
            trip_descriptor.start_time = self._localize_start_time(trip.start_date, trip.start_time)
            trip_descriptor.start_date = trip.start_date

            trip_schedule_relationship = self._trip_schedule_relationship_to_enum(trip.schedule_relationship)
            if trip_schedule_relationship is not None:
                trip_descriptor.schedule_relationship = trip_schedule_relationship

            if vehicle_model.vehicle_id:
                vehicle_descriptor = vehicle_position.vehicle
                vehicle_descriptor.id = self._vehicle_id_value(vehicle_model)
                vehicle_descriptor.label = vehicle_model.vehicle_label
                vehicle_descriptor.license_plate = vehicle_model.vehicle_license_plate

                wheelchair_accessible = self._wheelchair_accessible_to_enum(
                    vehicle_model.vehicle_wheelchair_accessible
                )
                if wheelchair_accessible is not None:
                    vehicle_descriptor.wheelchair_accessible = wheelchair_accessible

            position = vehicle_position.position
            position.latitude = vehicle_model.latitude
            position.longitude = vehicle_model.longitude

            vehicle_status = self._vehicle_stop_status_to_enum(vehicle_model.current_status)
            if vehicle_status is not None:
                vehicle_position.current_status = vehicle_status

            congestion_level = self._congestion_level_to_enum(vehicle_model.congestion_level)
            if congestion_level is not None:
                vehicle_position.congestion_level = congestion_level

        return feed
