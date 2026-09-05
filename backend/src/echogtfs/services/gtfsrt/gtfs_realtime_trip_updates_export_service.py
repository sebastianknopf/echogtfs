from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.protobuf.json_format import MessageToDict

from echogtfs import gtfs_realtime_pb2
from echogtfs.enum.gtfsrt import WheelchairAccessible
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.database.models import AppSetting, StopEvent, Trip
from echogtfs.services.gtfsrt.intf_gtfs_realtime_export import GtfsRealtimeExportInterface


class GtfsRealtimeTripUpdatesExportService(GtfsRealtimeExportInterface):
    """GTFS-Realtime export service for TripUpdate objects."""

    def __init__(
        self,
        repository: RealtimeRepositoryInterface,
        system_repository: SystemRepositoryInterface,
    ):
        self._repository = repository
        self._system_repository = system_repository
        self._target_timezone = self._resolve_timezone(self._configured_timezone_name())

    async def export_protobuf(self) -> bytes:
        """Export active Trip entities as GTFS-RT protobuf payload."""
        trips = await self._load_trips()
        feed = self._build_feed_message(trips)

        return feed.SerializeToString()

    async def export_json(self) -> bytes:
        """Export active Trip entities as GTFS-RT JSON payload."""
        trips = await self._load_trips()
        feed = self._build_feed_message(trips)
        feed_dict = MessageToDict(
            feed,
            preserving_proto_field_name=True,
            use_integers_for_enums=False,
        )

        return json.dumps(feed_dict, indent=2).encode("utf-8")

    async def _load_trips(self) -> list[Trip]:
        """Load active Trip entities with their stop events and vehicle relations."""
        trips = list(await self._repository.get_realtime_trips())
        exclude_value = await self._system_repository.get_app_setting(
            AppSetting.KEY_GTFS_RT_TRIP_UPDATES_EXCLUDE_TRIPS_WITHOUT_REALTIME_DATA
        )
        
        if exclude_value is None or exclude_value.strip().lower() != "true":
            return trips

        return [trip for trip in trips if self._has_realtime_stop_event(trip) or self._is_canceled_trip(trip)]

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
    def _stop_sequence_value(stop_event: StopEvent) -> int | None:
        try:
            return int(stop_event.stop_sequence)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _timestamp_value(value) -> int | None:
        if value is None:
            return None
        if hasattr(value, "timestamp"):
            return int(value.timestamp())
        
        return int(value)

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
    def _schedule_relationship_text(value: object | None) -> str | None:
        if value is None:
            return None

        text = value.value if hasattr(value, "value") else str(value)
        normalized = text.strip().upper()
        if not normalized:
            return None

        return normalized

    def _has_realtime_stop_event(self, trip_model: Trip) -> bool:
        return any(
            self._schedule_relationship_text(stop_event.schedule_relationship)
            in {"SCHEDULED", "SKIPPED"}
            for stop_event in trip_model.stop_events
        )

    def _is_canceled_trip(self, trip_model: Trip) -> bool:
        return self._schedule_relationship_text(trip_model.schedule_relationship) == "CANCELED"

    # GTFS-RT StopTimeUpdate only defines these relationships; anything else is not exposed.
    _EXPORTABLE_STOP_TIME_SCHEDULE_RELATIONSHIPS = {"SCHEDULED", "SKIPPED", "NO_DATA"}

    @classmethod
    def _stop_time_schedule_relationship_to_enum(
        cls,
        value: object | None,
        *,
        allow_added_stops: bool = False,
    ) -> int | None:
        text = cls._schedule_relationship_text(value)
        if allow_added_stops and text == "ADDED":
            text = "SCHEDULED"

        if text not in cls._EXPORTABLE_STOP_TIME_SCHEDULE_RELATIONSHIPS:
            return None

        return gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.ScheduleRelationship.Value(text)

    @classmethod
    def _exportable_stop_events(
        cls,
        trip_model: Trip,
        *,
        allow_added_stops: bool,
    ) -> list[StopEvent]:
        """Return stop events eligible for export, ordered by their source stop sequence."""
        stop_events = [
            stop_event
            for stop_event in trip_model.stop_events
            if allow_added_stops
            or cls._schedule_relationship_text(stop_event.schedule_relationship) != "ADDED"
        ]

        return sorted(stop_events, key=lambda item: cls._stop_sequence_value(item) or 0)

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
    def _normalize_start_date(start_date: object) -> str:
        if not isinstance(start_date, str):
            return ""

        value = start_date.strip()
        if not value:
            return ""

        try:
            return datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d")
        except ValueError:
            pass

        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError:
            return value

    def _build_feed_message(self, trips: list[Trip]) -> gtfs_realtime_pb2.FeedMessage:
        """Build GTFS-RT FeedMessage from Trip models."""
        feed = gtfs_realtime_pb2.FeedMessage()

        feed.header.gtfs_realtime_version = "2.0"
        feed.header.incrementality = gtfs_realtime_pb2.FeedHeader.FULL_DATASET
        feed.header.timestamp = int(time.time())

        for trip_model in trips:
            trip_schedule_relationship_text = self._schedule_relationship_text(trip_model.schedule_relationship)
            defines_full_stop_sequence = trip_schedule_relationship_text in {"NEW", "REPLACEMENT"}
            stop_events = self._exportable_stop_events(
                trip_model,
                allow_added_stops=defines_full_stop_sequence,
            )
            if not stop_events and trip_schedule_relationship_text not in {"DELETED", "CANCELED"}:
                continue

            entity = feed.entity.add()
            entity.id = str(trip_model.id)

            trip_update = entity.trip_update
            trip_update.timestamp = self._timestamp_value(trip_model.updated_at) or int(time.time())

            trip_descriptor = trip_update.trip
            trip_descriptor.trip_id = trip_model.trip_id
            trip_descriptor.route_id = trip_model.route_id
            trip_descriptor.start_time = self._localize_start_time(trip_model.start_date, trip_model.start_time)
            trip_descriptor.start_date = self._normalize_start_date(trip_model.start_date)

            trip_schedule_relationship = self._trip_schedule_relationship_to_enum(trip_model.schedule_relationship)
            if trip_schedule_relationship is not None:
                trip_descriptor.schedule_relationship = trip_schedule_relationship

            if trip_model.vehicle is not None:
                vehicle_descriptor = trip_update.vehicle
                vehicle_id_value = str(
                    getattr(trip_model.vehicle, "vehicle_id", None)
                    or trip_model.vehicle.id
                )
                vehicle_descriptor.id = vehicle_id_value

                if trip_model.vehicle.vehicle_label is not None:
                    vehicle_descriptor.label = trip_model.vehicle.vehicle_label

                if trip_model.vehicle.vehicle_license_plate is not None:
                    vehicle_descriptor.license_plate = trip_model.vehicle.vehicle_license_plate

                wheelchair_accessible = self._wheelchair_accessible_to_enum(
                    trip_model.vehicle.vehicle_wheelchair_accessible
                )

                if wheelchair_accessible is not None:
                    vehicle_descriptor.wheelchair_accessible = wheelchair_accessible

            for stop_sequence, stop_event in enumerate(stop_events, start=1):
                stop_time_update = trip_update.stop_time_update.add()
                stop_time_update.stop_id = stop_event.stop_id
                stop_time_update.stop_sequence = stop_sequence

                stop_time_relationship = self._stop_time_schedule_relationship_to_enum(
                    stop_event.schedule_relationship,
                    allow_added_stops=defines_full_stop_sequence,
                )
                if stop_time_relationship is not None:
                    stop_time_update.schedule_relationship = stop_time_relationship

                is_no_data = (
                    self._schedule_relationship_text(stop_event.schedule_relationship) == "NO_DATA"
                )
                if is_no_data and not defines_full_stop_sequence:
                    continue

                if stop_event.arrival_time is not None:
                    stop_time_update.arrival.time = self._timestamp_value(stop_event.arrival_time)

                if stop_event.departure_time is not None:
                    stop_time_update.departure.time = self._timestamp_value(stop_event.departure_time)

        return feed
