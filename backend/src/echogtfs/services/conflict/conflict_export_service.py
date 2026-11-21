from __future__ import annotations

import logging
import os
from hashlib import sha256
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from echogtfs.common.config import settings
from echogtfs.common.global_id import GlobalId
from echogtfs.enum.conflicts import ConflictType
from echogtfs.enum.system import DataSourceExecutionType
from echogtfs.services.conflict.intf_conflict_export_service import ConflictExportServiceInterface
from echogtfs.services.database.realtime_models import VehiclePosition
from echogtfs.services.database.realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.system_repository import SystemRepositoryInterface
from echogtfs.validation.schemas import MonitoringConflictObject, MonitoringDatasourceGroupObject

logger = logging.getLogger("uvicorn")


class ConflictExportService(ConflictExportServiceInterface):

    # Grace period after the cron-scheduled time before an overdue time-based datasource is reported as a failure
    OVERDUE_GRACE_PERIOD = timedelta(minutes=5)

    def __init__(self, system_repository: SystemRepositoryInterface, realtime_repository: RealtimeRepositoryInterface):
        self._system_repository = system_repository
        self._realtime_repository = realtime_repository
        self._scheduler_timezone = self._resolve_scheduler_timezone()

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

        # select time-based datasources which are overdue based on their cron schedule
        now: datetime = datetime.now(self._scheduler_timezone)
        for ds in await self._system_repository.list_active_data_sources_with_cron():
            if not ds.is_active:
                continue

            if ds.execution_type != DataSourceExecutionType.TIME_BASED:
                continue

            if filter_datasource_id is not None and ds.id != filter_datasource_id:
                continue

            expected_run_at = self._expected_datasource_run_at(ds)
            if expected_run_at is None or now < expected_run_at + self.OVERDUE_GRACE_PERIOD:
                continue

            self._add_conflict(MonitoringConflictObject(
                id=self._unique_conflict_id(datasource_id=ds.id, conflict_type=ConflictType.ERROR_DATASOURCE_FAILURE),
                timestamp=expected_run_at,
                code=ConflictType.ERROR_DATASOURCE_FAILURE,
                message=ConflictType.ERROR_DATASOURCE_FAILURE.name,
                datasource=MonitoringDatasourceGroupObject(
                    id=ds.id,
                    name=ds.name,
                ),
                properties={
                    "datasource_id": ds.id,
                    "datasource_name": ds.name,
                    "last_run_at": ds.last_run_at,
                    "expected_run_at": expected_run_at
                }
            ), results)

        # find invalid references for service alerts
        for ie in await self._realtime_repository.list_informed_entities_with_invalid_references():
            if filter_datasource_id is None or ie.alert.data_source_id == filter_datasource_id:
                datasource_id: int | None = ie.alert.data_source_id
                timestamp: datetime = ie.alert.created_at

                if not ie.is_agency_valid:
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, agency_id=ie.agency_id, conflict_type=ConflictType.ERROR_NO_AGENCY_FOUND),
                        timestamp=timestamp,
                        code=ConflictType.ERROR_NO_AGENCY_FOUND,
                        message=ConflictType.ERROR_NO_AGENCY_FOUND.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=ie.alert.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "agency_id": ie.agency_id
                        }
                    ), results)

                if not ie.is_stop_valid:
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, stop_id=ie.stop_id, conflict_type=ConflictType.ERROR_NO_STOP_FOUND),
                        timestamp=timestamp,
                        code=ConflictType.ERROR_NO_STOP_FOUND,
                        message=ConflictType.ERROR_NO_STOP_FOUND.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=ie.alert.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "stop_id": ie.stop_id
                        }
                    ), results)

                if not ie.is_route_valid:
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, route_id=ie.route_id, conflict_type=ConflictType.ERROR_NO_ROUTE_FOUND),
                        timestamp=timestamp,
                        code=ConflictType.ERROR_NO_ROUTE_FOUND,
                        message=ConflictType.ERROR_NO_ROUTE_FOUND.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=ie.alert.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "route_id": ie.route_id
                        }
                    ), results)

                if not ie.is_trip_valid:
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, trip_id=ie.trip_id, conflict_type=ConflictType.ERROR_NO_TRIP_FOUND),
                        timestamp=timestamp,
                        code=ConflictType.ERROR_NO_TRIP_FOUND,
                        message=ConflictType.ERROR_NO_TRIP_FOUND.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=ie.alert.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "trip_id": ie.trip_id
                        }
                    ), results) 


        # find invalid stops for trip updates
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

        # find invalid routes and trips for trip updates
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
                            "scheduled_end_time": trip.scheduled_end_time,
                            "assignment_type": trip.assignment_type
                        }
                    ), results)  

        # find invalid references for vehicle positions
        for vehicle in await self._realtime_repository.list_vehicles_with_invalid_references():
            if filter_datasource_id is None or vehicle.data_source_id == filter_datasource_id:
                datasource_id = vehicle.data_source_id
                timestamp = vehicle.created_at
                vehicle_display_title = self._vehicle_display_title(vehicle)
                datasource = MonitoringDatasourceGroupObject(
                    id=datasource_id,
                    name=vehicle.data_source_name,
                )

                if not vehicle.is_stop_valid:
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(
                            datasource_id=datasource_id,
                            vehicle_position_id=vehicle.id,
                            stop_id=vehicle.stop_id,
                            conflict_type=ConflictType.ERROR_NO_STOP_FOUND,
                        ),
                        timestamp=timestamp,
                        code=ConflictType.ERROR_NO_STOP_FOUND,
                        message=ConflictType.ERROR_NO_STOP_FOUND.name,
                        datasource=datasource,
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "stop_id": vehicle.stop_id,
                            "vehicle_id": vehicle_display_title,
                        }
                    ), results)

                if not vehicle.trip.is_route_valid:
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(
                            datasource_id=datasource_id,
                            vehicle_position_id=vehicle.id,
                            route_id=vehicle.trip.route_id,
                            conflict_type=ConflictType.ERROR_NO_ROUTE_FOUND,
                        ),
                        timestamp=timestamp,
                        code=ConflictType.ERROR_NO_ROUTE_FOUND,
                        message=ConflictType.ERROR_NO_ROUTE_FOUND.name,
                        datasource=datasource,
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "route_id": vehicle.trip.route_id,
                            "vehicle_id": vehicle_display_title,
                        }
                    ), results)

                if not vehicle.trip.is_trip_valid:
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(
                            datasource_id=datasource_id,
                            vehicle_position_id=vehicle.id,
                            trip_id=vehicle.trip.trip_id,
                            conflict_type=ConflictType.ERROR_NO_TRIP_FOUND,
                        ),
                        timestamp=timestamp,
                        code=ConflictType.ERROR_NO_TRIP_FOUND,
                        message=ConflictType.ERROR_NO_TRIP_FOUND.name,
                        datasource=datasource,
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "trip_id": vehicle.trip.trip_id,
                            "vehicle_id": vehicle_display_title,
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

        # find references with non-global IDs for service alerts
        for ie in await self._realtime_repository.list_informed_entities_with_non_global_ids(settings.global_id_pattern):
            if filter_datasource_id is None or ie.alert.data_source_id == filter_datasource_id:
                datasource_id: int | None = ie.alert.data_source_id
                timestamp: datetime = ie.alert.created_at

                agency_id = ie.original_agency_id if ie.original_agency_id is not None else ie.agency_id
                if agency_id is not None and not GlobalId.is_global_id(agency_id):
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, original_agency_id=agency_id, conflict_type=ConflictType.WARNING_AGENCY_NO_GLOBAL_ID, last_failure=timestamp),
                        timestamp=timestamp,
                        code=ConflictType.WARNING_AGENCY_NO_GLOBAL_ID,
                        message=ConflictType.WARNING_AGENCY_NO_GLOBAL_ID.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=ie.alert.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "original_agency_id": agency_id
                        }
                    ), results)

                stop_id = ie.original_stop_id if ie.original_stop_id is not None else ie.stop_id
                if stop_id is not None and not GlobalId.is_global_id(stop_id):
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, original_stop_id=stop_id, conflict_type=ConflictType.WARNING_STOP_NO_GLOBAL_ID, last_failure=timestamp),
                        timestamp=timestamp,
                        code=ConflictType.WARNING_STOP_NO_GLOBAL_ID,
                        message=ConflictType.WARNING_STOP_NO_GLOBAL_ID.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=ie.alert.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "original_stop_id": stop_id
                        }
                    ), results)

                route_id = ie.original_route_id if ie.original_route_id is not None else ie.route_id
                if route_id is not None and not GlobalId.is_global_id(route_id):
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, original_route_id=route_id, conflict_type=ConflictType.WARNING_ROUTE_NO_GLOBAL_ID, last_failure=timestamp),
                        timestamp=timestamp,
                        code=ConflictType.WARNING_ROUTE_NO_GLOBAL_ID,
                        message=ConflictType.WARNING_ROUTE_NO_GLOBAL_ID.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=ie.alert.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "original_route_id": route_id
                        }
                    ), results)

                trip_id = ie.original_trip_id if ie.original_trip_id is not None else ie.trip_id
                if trip_id is not None and not GlobalId.is_global_id(trip_id):
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, original_trip_id=trip_id, conflict_type=ConflictType.WARNING_TRIP_NO_GLOBAL_ID, last_failure=timestamp),
                        timestamp=timestamp,
                        code=ConflictType.WARNING_TRIP_NO_GLOBAL_ID,
                        message=ConflictType.WARNING_TRIP_NO_GLOBAL_ID.name,
                        datasource=MonitoringDatasourceGroupObject(
                            id=datasource_id,
                            name=ie.alert.data_source_name,
                        ),
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "original_trip_id": trip_id
                        }
                    ), results)

        # find stops with non-global IDs for trip updates
        for ste in await self._realtime_repository.list_stop_events_with_non_global_ids(settings.global_id_pattern):
            if filter_datasource_id is None or ste.trip.data_source_id == filter_datasource_id:
                datasource_id: int = ste.trip.data_source_id
                timestamp: datetime = ste.trip.created_at

                self._add_conflict(MonitoringConflictObject(
                    id=self._unique_conflict_id(datasource_id=datasource_id, original_stop_id=ste.original_stop_id, conflict_type=ConflictType.WARNING_STOP_NO_GLOBAL_ID, last_failure=timestamp),
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
                        "original_stop_id": ste.original_stop_id
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

                if not GlobalId.is_global_id(trip.original_trip_id):
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(datasource_id=datasource_id, original_trip_id=trip.original_trip_id, conflict_type=ConflictType.WARNING_TRIP_NO_GLOBAL_ID, last_failure=timestamp),
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
                            "original_trip_id": trip.original_trip_id
                        }
                    ), results)

        # find stop, route and trip IDs with non-global IDs for vehicle positions
        for vehicle in await self._realtime_repository.list_vehicles_with_non_global_ids(settings.global_id_pattern):
            if filter_datasource_id is None or vehicle.data_source_id == filter_datasource_id:
                datasource_id = vehicle.data_source_id
                timestamp = vehicle.created_at
                vehicle_display_title = self._vehicle_display_title(vehicle)
                datasource = MonitoringDatasourceGroupObject(
                    id=datasource_id,
                    name=vehicle.data_source_name,
                )

                if vehicle.stop_id is not None and not GlobalId.is_global_id(vehicle.stop_id):
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(
                            datasource_id=datasource_id,
                            vehicle_position_id=vehicle.id,
                            stop_id=vehicle.stop_id,
                            conflict_type=ConflictType.WARNING_STOP_NO_GLOBAL_ID,
                        ),
                        timestamp=timestamp,
                        code=ConflictType.WARNING_STOP_NO_GLOBAL_ID,
                        message=ConflictType.WARNING_STOP_NO_GLOBAL_ID.name,
                        datasource=datasource,
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "stop_id": vehicle.stop_id,
                            "vehicle_id": vehicle_display_title,
                        }
                    ), results)

                if not GlobalId.is_global_id(vehicle.trip.route_id):
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(
                            datasource_id=datasource_id,
                            vehicle_position_id=vehicle.id,
                            route_id=vehicle.trip.route_id,
                            conflict_type=ConflictType.WARNING_ROUTE_NO_GLOBAL_ID,
                        ),
                        timestamp=timestamp,
                        code=ConflictType.WARNING_ROUTE_NO_GLOBAL_ID,
                        message=ConflictType.WARNING_ROUTE_NO_GLOBAL_ID.name,
                        datasource=datasource,
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "route_id": vehicle.trip.route_id,
                            "vehicle_id": vehicle_display_title,
                        }
                    ), results)

                if not GlobalId.is_global_id(vehicle.trip.original_trip_id):
                    self._add_conflict(MonitoringConflictObject(
                        id=self._unique_conflict_id(
                            datasource_id=datasource_id,
                            vehicle_position_id=vehicle.id,
                            original_trip_id=vehicle.trip.original_trip_id,
                            conflict_type=ConflictType.WARNING_TRIP_NO_GLOBAL_ID,
                        ),
                        timestamp=timestamp,
                        code=ConflictType.WARNING_TRIP_NO_GLOBAL_ID,
                        message=ConflictType.WARNING_TRIP_NO_GLOBAL_ID.name,
                        datasource=datasource,
                        properties={
                            "datasource_id": datasource_id,
                            "last_failure": timestamp,
                            "original_trip_id": vehicle.trip.original_trip_id,
                            "vehicle_id": vehicle_display_title,
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

    @staticmethod
    def _resolve_scheduler_timezone() -> ZoneInfo:
        timezone_name = os.getenv("TIMEZONE", "UTC").strip() or "UTC"

        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning("[ConflictExportService] Unknown TIMEZONE '%s'. Falling back to UTC", timezone_name)
            return ZoneInfo("UTC")

    def _build_cron_trigger(self, cron_expr: str) -> CronTrigger:
        fields = cron_expr.split()
        if len(fields) == 5:
            return CronTrigger.from_crontab(cron_expr, timezone=self._scheduler_timezone)

        if len(fields) == 6:
            second, minute, hour, day, month, day_of_week = fields
            return CronTrigger(
                second=second,
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone=self._scheduler_timezone,
            )

        raise ValueError("Cron expression must have 5 fields (minute-level) or 6 fields (second-level)")

    def _expected_datasource_run_at(self, ds) -> datetime | None:
        """Return the cron-scheduled time a time-based data source should have run at next, or None if undetermined."""
        if not ds.cron:
            return None

        try:
            trigger = self._build_cron_trigger(ds.cron)
        except ValueError:
            logger.warning(
                "[ConflictExportService] Invalid cron expression for data source '%s': %s",
                ds.name,
                ds.cron,
            )
            return None

        reference = ds.last_run_at or ds.created_at
        return trigger.get_next_fire_time(reference, reference)

    def _unique_conflict_id(self, **kwargs) -> str:
        """Generate a unique conflict identifier based on provided keyword arguments."""

        return sha256("_".join(f"{key}={value}" for key, value in sorted(kwargs.items())).encode()).hexdigest()

    @staticmethod
    def _vehicle_display_title(vehicle: VehiclePosition) -> str:
        def clean(value: str | None) -> str:
            return "" if value is None else str(value).strip()

        parts = [
            clean(vehicle.vehicle_license_plate),
            clean(vehicle.vehicle_label),
        ]
        title = " - ".join(part for part in parts if part)
        return title or clean(vehicle.vehicle_id) or "Vehicle"

    def _conflict_exists(self, conflict_id: str, existing_conflicts: list[MonitoringConflictObject]) -> bool:
        """Check if a conflict with the given ID already exists in the list of existing conflicts."""
        return any(conflict.id == conflict_id for conflict in existing_conflicts)

    def _add_conflict(self, conflict: MonitoringConflictObject, existing_conflicts: list[MonitoringConflictObject]) -> None:
        """Add a conflict to the list of existing conflicts if it doesn't already exist."""
        if not self._conflict_exists(conflict.id, existing_conflicts):
            existing_conflicts.append(conflict)