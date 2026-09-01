from __future__ import annotations

from hashlib import sha256
from datetime import datetime

from echogtfs.common.config import settings
from echogtfs.common.global_id import GlobalId
from echogtfs.enum.conflicts import ConflictType
from echogtfs.services.conflict.intf_conflict_export_service import ConflictExportServiceInterface
from echogtfs.services.database.realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.system_repository import SystemRepositoryInterface
from echogtfs.validation.schemas import MonitoringConflictObject, MonitoringDatasourceGroupObject


class ConflictExportService(ConflictExportServiceInterface):

    def __init__(self, system_repository: SystemRepositoryInterface, realtime_repository: RealtimeRepositoryInterface):
        self._system_repository = system_repository
        self._realtime_repository = realtime_repository

    async def export(self, filter_datasource_id: int | None = None) -> list[MonitoringConflictObject]:
        results: list[MonitoringConflictObject] = []

        # select datasource failures
        for ds in await self._system_repository.list_data_sources_with_failures(min_num_failures=5):
            if filter_datasource_id is None or ds.id == filter_datasource_id:
                last_failure: datetime = ds.logs[0].timestamp

                self._add_conflict(MonitoringConflictObject(
                    id=self._unique_conflict_id(datasource_id=ds.id, conflict_type=ConflictType.ERROR_DATASOURCE_FAILURE),
                    timestamp=last_failure,
                    code=ConflictType.ERROR_DATASOURCE_FAILURE,
                    message=ConflictType.ERROR_DATASOURCE_FAILURE.name,
                    datasource=MonitoringDatasourceGroupObject(
                        id=ds.id,
                        name=ds.name,
                    ),
                    properties={
                        "datasource_id": ds.id,
                        "last_status": ds.logs[0].status_code,
                        "last_failure": last_failure
                    }
                ), results)

        # find invalid stops
        for ste in await self._realtime_repository.list_stop_events_with_invalid_references():
            if filter_datasource_id is None or ste.trip.data_source_id == filter_datasource_id:
                datasource_id: int = ste.trip.data_source_id
                timestamp: datetime = ste.trip.created_at

                self._add_conflict(MonitoringConflictObject(
                    id=self._unique_conflict_id(datasource_id=datasource_id, stop_id=ste.stop_id, conflict_type=ConflictType.ERROR_NO_STOP_FOUND),
                    timestamp=timestamp,
                    code=ConflictType.ERROR_NO_STOP_FOUND,
                    message=ConflictType.ERROR_NO_STOP_FOUND.name,
                    datasource=MonitoringDatasourceGroupObject(
                        id=datasource_id,
                        name=ste.trip.data_source_name,
                    ),
                    properties={
                        "datasource_id": datasource_id,
                        "last_failure": timestamp,
                        "stop_id": ste.stop_id
                    }
                ), results)

        # find invalid routes and trips
        for trip in await self._realtime_repository.list_trips_with_invalid_references():
            if filter_datasource_id is None or trip.data_source_id == filter_datasource_id:
                datasource_id: int = trip.data_source_id
                timestamp: datetime = trip.created_at

                if not trip.is_route_valid:
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, route_id=trip.route_id, conflict_type=ConflictType.ERROR_NO_ROUTE_FOUND),
                        timestamp=timestamp,
                        code=ConflictType.ERROR_NO_ROUTE_FOUND,
                        message=ConflictType.ERROR_NO_ROUTE_FOUND.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=trip.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "route_id": trip.route_id
                        }
                    ), results)

                if not trip.is_trip_valid:
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, trip_id=trip.trip_id, conflict_type=ConflictType.ERROR_NO_TRIP_FOUND),
                        timestamp=timestamp,
                        code=ConflictType.ERROR_NO_TRIP_FOUND,
                        message=ConflictType.ERROR_NO_TRIP_FOUND.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=trip.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "trip_id": trip.trip_id,
                            "scheduled_start_stop_id": trip.scheduled_start_stop_id,
                            "scheduled_start_time": trip.scheduled_start_time,
                            "scheduled_end_stop_id": trip.scheduled_end_stop_id,
                            "scheduled_end_time": trip.scheduled_end_time
                        }
                    ), results)  

        # find stop events with implied schedule relationships ADDED and SKIPPED
        for ste in await self._realtime_repository.list_stop_events_with_implied_deviation_schedule_relationships():
            if filter_datasource_id is None or ste.trip.data_source_id == filter_datasource_id:
                datasource_id: int = ste.trip.data_source_id
                timestamp: datetime = ste.trip.created_at

                if ste.schedule_relationship == "ADDED":
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, trip_id=ste.trip.trip_id, stop_id=ste.stop_id, stop_sequence=ste.stop_sequence, conflict_type=ConflictType.WARNING_IMPLIED_ADDITIONAL_STOP),
                        timestamp=timestamp,
                        code=ConflictType.WARNING_IMPLIED_ADDITIONAL_STOP,
                        message=ConflictType.WARNING_IMPLIED_ADDITIONAL_STOP.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=ste.trip.data_source_name,
                        ),
                        properties={
                            "datasource_id": ste.trip.data_source_id,
                            "last_failure": timestamp,
                            "trip_id": ste.trip.trip_id,
                            "stop_id": ste.stop_id,
                            "stop_sequence": ste.stop_sequence
                        }
                    ), results)

                if ste.schedule_relationship == "SKIPPED":
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, trip_id=ste.trip.trip_id, stop_id=ste.stop_id, stop_sequence=ste.stop_sequence, conflict_type=ConflictType.WARNING_IMPLIED_CANCELED_STOP),
                        timestamp=timestamp,
                        code=ConflictType.WARNING_IMPLIED_CANCELED_STOP,
                        message=ConflictType.WARNING_IMPLIED_CANCELED_STOP.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=ste.trip.data_source_name,
                        ),
                        properties={
                            "datasource_id": ste.trip.data_source_id,
                            "last_failure": timestamp,
                            "trip_id": ste.trip.trip_id,
                            "stop_id": ste.stop_id,
                            "stop_sequence": ste.stop_sequence
                        }
                    ), results)

        # find stops where the quay might have been corrected by the system
        for ste in await self._realtime_repository.list_stop_events_with_changed_stop_id():
            if filter_datasource_id is None or ste.trip.data_source_id == filter_datasource_id:
                datasource_id: int = ste.trip.data_source_id
                timestamp: datetime = ste.trip.created_at

                self._add_conflict(MonitoringConflictObject(
                    id=self._unique_conflict_id(datasource_id=datasource_id, trip_id=ste.trip.trip_id, stop_id=ste.stop_id, stop_sequence=ste.stop_sequence, conflict_type=ConflictType.WARNING_WRONG_QUAY),
                    timestamp=timestamp,
                    code=ConflictType.WARNING_WRONG_QUAY,
                    message=ConflictType.WARNING_WRONG_QUAY.name,
                    datasource=MonitoringDatasourceGroupObject(
                        id=datasource_id,
                        name=ste.trip.data_source_name,
                    ),
                    properties={
                        "datasource_id": datasource_id,
                        "last_failure": timestamp,
                        "trip_id": ste.trip.trip_id,
                        "stop_id": ste.stop_id,
                        "stop_sequence": ste.stop_sequence,
                        "original_stop_id": ste.original_stop_id
                    }
                ), results)

        # find stops with non-global IDs ...
        for ste in await self._realtime_repository.list_stop_events_with_non_global_ids(settings.global_id_pattern):
            if filter_datasource_id is None or ste.trip.data_source_id == filter_datasource_id:
                datasource_id: int = ste.trip.data_source_id
                timestamp: datetime = ste.trip.created_at

                self._add_conflict(MonitoringConflictObject(
                    id=self._unique_conflict_id(datasource_id=datasource_id, stop_id=ste.stop_id, conflict_type=ConflictType.WARNING_STOP_NO_GLOBAL_ID, last_failure=timestamp),
                    timestamp=timestamp,
                    code=ConflictType.WARNING_STOP_NO_GLOBAL_ID,
                    message=ConflictType.WARNING_STOP_NO_GLOBAL_ID.name,
                    datasource=MonitoringDatasourceGroupObject(
                        id=datasource_id,
                        name=ste.trip.data_source_name,
                    ),
                    properties={
                        "datasource_id": datasource_id,
                        "last_failure": timestamp,
                        "stop_id": ste.stop_id
                    }
                ), results)

        # find routes and trips with non-global IDs
        for trip in await self._realtime_repository.list_trips_with_non_global_ids(settings.global_id_pattern):
            if filter_datasource_id is None or trip.data_source_id == filter_datasource_id:
                datasource_id: int = trip.data_source_id
                timestamp: datetime = trip.created_at

                if not GlobalId.is_global_id(trip.route_id):
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, route_id=trip.route_id, conflict_type=ConflictType.WARNING_ROUTE_NO_GLOBAL_ID, last_failure=timestamp),
                        timestamp=timestamp,
                        code=ConflictType.WARNING_ROUTE_NO_GLOBAL_ID,
                        message=ConflictType.WARNING_ROUTE_NO_GLOBAL_ID.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=trip.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "route_id": trip.route_id
                        }
                    ), results)

                if not GlobalId.is_global_id(trip.trip_id):
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, trip_id=trip.trip_id, conflict_type=ConflictType.WARNING_TRIP_NO_GLOBAL_ID, last_failure=timestamp),
                        timestamp=timestamp,
                        code=ConflictType.WARNING_TRIP_NO_GLOBAL_ID,
                        message=ConflictType.WARNING_TRIP_NO_GLOBAL_ID.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=trip.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "trip_id": trip.trip_id
                        }
                    ), results)

        # find stop events with departure before arrival errors
        for ste in await self._realtime_repository.list_stop_events_with_departure_before_arrival():
            if filter_datasource_id is None or ste.trip.data_source_id == filter_datasource_id:
                datasource_id: int = ste.trip.data_source_id
                timestamp: datetime = ste.trip.created_at

                self._add_conflict(MonitoringConflictObject(
                    id=self._unique_conflict_id(datasource_id=datasource_id, trip_id=ste.trip_id, stop_id=ste.stop_id, stop_sequence=ste.stop_sequence, conflict_type=ConflictType.WARNING_PREMATURE_DEPARTURE, last_failure=timestamp),
                    timestamp=timestamp,
                    code=ConflictType.WARNING_PREMATURE_DEPARTURE,
                    message=ConflictType.WARNING_PREMATURE_DEPARTURE.name,
                    datasource=MonitoringDatasourceGroupObject(
                        id=datasource_id,
                        name=ste.trip.data_source_name,
                    ),
                    properties={
                        "datasource_id": datasource_id,
                        "last_failure": timestamp,
                        "trip_id": ste.trip.trip_id,
                        "stop_id": ste.stop_id,
                        "stop_sequence": ste.stop_sequence
                    }
                ), results)

        # finally return the sorted conflict objects
        return sorted(results, key=lambda x: x.timestamp, reverse=True)

    def _unique_conflict_id(self, **kwargs) -> str:
        """Generate a unique conflict identifier based on provided keyword arguments."""

        return sha256("_".join(f"{key}={value}" for key, value in sorted(kwargs.items())).encode()).hexdigest()

    def _conflict_exists(self, conflict_id: str, existing_conflicts: list[MonitoringConflictObject]) -> bool:
        """Check if a conflict with the given ID already exists in the list of existing conflicts."""
        return any(conflict.id == conflict_id for conflict in existing_conflicts)

    def _add_conflict(self, conflict: MonitoringConflictObject, existing_conflicts: list[MonitoringConflictObject]) -> None:
        """Add a conflict to the list of existing conflicts if it doesn't already exist."""
        if not self._conflict_exists(conflict.id, existing_conflicts):
            existing_conflicts.append(conflict)