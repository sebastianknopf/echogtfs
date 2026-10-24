from __future__ import annotations

import logging
import uuid
from typing import Any

from echogtfs.enum.gtfsrt import AssignmentType
from echogtfs.enum.system import InvalidReferencePolicy
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.matching.matching_service import MatchingService

logger = logging.getLogger("uvicorn")

from .base import RealtimeProcessingServiceBase


class VehiclePositionProcessingService(RealtimeProcessingServiceBase):
    MAX_INTERMEDIATE_STOP_SAMPLE_SIZE = 3

    @staticmethod
    def _extract_vehicle_trip_payload(record: dict[str, Any]) -> dict[str, Any]:
        """Normalize vehicle trip payload from flat or nested dialect shapes."""
        payload = record.get("trip", {})
        if not isinstance(payload, dict):
            payload = {}

        trip_id_value = record.get("trip_id") or payload.get("trip_id")
        if not trip_id_value:
            raise ValueError("Vehicle-position record is missing trip reference ('trip_id' or 'trip.trip_id')")

        return {
            "trip_id": str(trip_id_value),
            "start_time": str(record.get("trip_start_time") or payload.get("start_time") or ""),
            "start_date": str(record.get("trip_start_date") or payload.get("start_date") or ""),
            "route_id": str(record.get("trip_route_id") or payload.get("route_id") or ""),
            "schedule_relationship": str(
                record.get("trip_schedule_relationship")
                or payload.get("schedule_relationship")
                or "SCHEDULED"
            ),
            "assignment_type": str(
                record.get("trip_assignment_type")
                or payload.get("assignment_type")
                or "ASSIGNED"
            ),
            "scheduled_start_stop_id": payload.get("scheduled_start_stop_id", record.get("scheduled_start_stop_id")),
            "scheduled_start_time": payload.get("scheduled_start_time", record.get("scheduled_start_time")),
            "scheduled_end_stop_id": payload.get("scheduled_end_stop_id", record.get("scheduled_end_stop_id")),
            "scheduled_end_time": payload.get("scheduled_end_time", record.get("scheduled_end_time")),
            "scheduled_intermediate_stops": payload.get(
                "scheduled_intermediate_stops", record.get("scheduled_intermediate_stops")
            ),
        }

    async def sync_records(
        self,
        repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
        source_id: int,
        source_name: str,
        records: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Synchronize vehicle-position records into the database."""
        policy = await repository.get_data_source_invalid_reference_policy(source_id)
        if isinstance(policy, str):
            policy = InvalidReferencePolicy(policy)

        is_differential_updates = await repository.get_data_source_is_differential_updates(source_id)

        logger.info(
            f"[{self.get_adapter_type()}] Synchronizing vehicle-position records from '{source_name}' "
            f"(policy: {policy.value})"
        )

        await self._identifier_mapping_service.initialize(repository, source_id)

        mapping_count = self._identifier_mapping_service.get_loaded_mapping_count()
        if mapping_count > 0:
            logger.info(
                f"[{self.get_adapter_type()}] Loaded {mapping_count} mapping entries"
            )

        gtfs_id_validator = self._create_gtfs_id_validator(gtfs_repository)
        vehicle_route_ids: set[object] = set()
        vehicle_trip_ids: set[object] = set()
        for record in records:
            try:
                record_trip_payload = self._extract_vehicle_trip_payload(record)
            except ValueError:
                continue

            vehicle_route_ids.add(
                self._identifier_mapping_service.apply_mapping(
                    {"route_id": record_trip_payload.get("route_id")}
                ).get("route_id")
            )

            vehicle_trip_ids.add(record_trip_payload.get("trip_id"))

        await gtfs_id_validator.prefetch("route", vehicle_route_ids)
        await gtfs_id_validator.prefetch("trip", vehicle_trip_ids)
        await gtfs_id_validator.prefetch("stop", (record.get("stop_id") for record in records))
        gtfs_entities = gtfs_id_validator.valid_ids()
        if self._matching_service is None:
            self._matching_service = MatchingService(gtfs_repository, self._caching_service)

        incoming_vehicle_ids = {
            self._record_uuid(record, source_name, fallback_key="vehicle_id", kind="Vehicle-position")
            for record in records
        }

        existing_vehicles = {
            vehicle.id: vehicle
            for vehicle in await realtime_repository.list_vehicles_for_data_source(source_id)
        }
        
        existing_vehicle_ids = set(existing_vehicles.keys())
        vehicle_uuid_by_trip_id = {
            str(vehicle.trip_id): vehicle.id
            for vehicle in existing_vehicles.values()
            if getattr(vehicle, "trip_id", None)
        }
        
        processed_vehicle_ids = set(existing_vehicle_ids)

        if incoming_vehicle_ids:
            vehicles_by_id = {
                vehicle.id: vehicle
                for vehicle in await realtime_repository.list_vehicles_by_ids(list(incoming_vehicle_ids))
            }
            
            for vehicle_id, vehicle in vehicles_by_id.items():
                if vehicle_id not in existing_vehicles:
                    existing_vehicles[vehicle_id] = vehicle
                    existing_vehicle_ids.add(vehicle_id)

        stats_created = 0
        stats_updated = 0
        stats_deleted = 0
        policy_based_deletes: set[uuid.UUID] = set()
        persisted_vehicle_uuids: set[uuid.UUID] = set()

        for record in records:
            vehicle_uuid = self._record_uuid(record, source_name, fallback_key="vehicle_id", kind="Vehicle-position")
            try:
                trip_payload = self._extract_vehicle_trip_payload(record)
            except ValueError as exc:
                logger.debug(
                    f"[{self.get_adapter_type()}] Discarding vehicle-position record due to invalid trip payload: {exc}"
                )
                
                continue

            mapped_trip = self._identifier_mapping_service.apply_mapping(
                {
                    "route_id": trip_payload.get("route_id"),
                }
            )
            trip_payload["route_id"] = str(mapped_trip.get("route_id") or "")
            route_is_valid = bool(trip_payload["route_id"]) and trip_payload["route_id"] in gtfs_entities.get("route", set())

            stop_reference_value = record.get("stop_id")
            stop_reference_is_valid = True
            if stop_reference_value:
                stop_reference_is_valid = str(stop_reference_value) in gtfs_entities.get("stop", set())

            derived_trip_id = trip_payload["trip_id"]
            resolved_trip_id = derived_trip_id
            is_new_trip = trip_payload["schedule_relationship"].upper() == "NEW"
            trip_assignment_type = AssignmentType.DIRECT_BY_ID.value
            trip_reference_is_valid = True if is_new_trip else derived_trip_id in gtfs_entities["trip"]
            matched_trip_id: str | None = None
            matched_assignment_type: AssignmentType | None = None
            match_inputs = self._map_scheduled_match_inputs(trip_payload)

            if not is_new_trip and not trip_reference_is_valid:
                matched_trip_id, matched_assignment_type = await self._matching_service.match(
                    trip_id=derived_trip_id,
                    route_id=trip_payload["route_id"] or None,
                    operation_day_date=self._parse_operation_day(trip_payload.get("start_date")),
                    **match_inputs,
                    is_complete_stop_sequence=bool(record.get("is_complete_stop_sequence", True)),
                    intermediate_stop_sample_size=self.MAX_INTERMEDIATE_STOP_SAMPLE_SIZE,
                )

                trip_assignment_type = matched_assignment_type.value

                if matched_trip_id is not None:
                    resolved_trip_id = matched_trip_id
                    trip_reference_is_valid = True

            has_invalid_reference = (not route_is_valid) or (not stop_reference_is_valid) or (not trip_reference_is_valid)

            should_skip_vehicle = False
            should_deactivate_vehicle = False

            if has_invalid_reference:
                if policy == InvalidReferencePolicy.DISCARD_ENTIRE_OBJECT:
                    should_skip_vehicle = True
                    if vehicle_uuid in existing_vehicle_ids:
                        policy_based_deletes.add(vehicle_uuid)

                elif policy in (
                    InvalidReferencePolicy.DISCARD_INVALID,
                    InvalidReferencePolicy.DISCARD_INVALID_ELEMENTS,
                ):
                    if not route_is_valid:
                        trip_payload["route_id"] = ""

                    has_any_valid_reference = (
                        trip_reference_is_valid
                        or bool(trip_payload["route_id"])
                        or stop_reference_is_valid
                    )
                    if (not trip_reference_is_valid) or (not has_any_valid_reference):
                        should_deactivate_vehicle = True

                elif policy == InvalidReferencePolicy.KEEP_OBJECT_DISABLED:
                    should_deactivate_vehicle = True

            if should_skip_vehicle:
                continue

            vehicle_is_active_on_create = bool(record.get("is_active", True))
            if should_deactivate_vehicle:
                vehicle_is_active_on_create = False

            trip_is_trip_valid = trip_reference_is_valid
            trip_is_route_valid = route_is_valid

            trip_payload["trip_id"] = resolved_trip_id
            trip_id_key = str(trip_payload["trip_id"])

            vehicle_uuid = vehicle_uuid_by_trip_id.get(trip_id_key)
            if vehicle_uuid is None:
                vehicle_uuid = self._record_uuid(
                    record,
                    source_name,
                    fallback_key="vehicle_id",
                    kind="Vehicle-position",
                )
                vehicle_uuid_by_trip_id[trip_id_key] = vehicle_uuid

            if vehicle_uuid in processed_vehicle_ids:
                stats_updated += 1
            else:
                stats_created += 1
                processed_vehicle_ids.add(vehicle_uuid)

            persisted_vehicle_uuids.add(vehicle_uuid)

            current_stop_sequence_raw = record.get("current_stop_sequence")
            try:
                current_stop_sequence = (
                    int(current_stop_sequence_raw)
                    if current_stop_sequence_raw is not None
                    else None
                )
            except (TypeError, ValueError):
                current_stop_sequence = None

            await realtime_repository.update_vehicle_position_from_sync(
                vehicle_uuid=vehicle_uuid,
                source_id=source_id,
                trip_id=trip_payload["trip_id"],
                trip_original_trip_id=derived_trip_id,
                trip_start_time=trip_payload["start_time"],
                trip_start_date=trip_payload["start_date"],
                trip_route_id=trip_payload["route_id"],
                trip_schedule_relationship=trip_payload["schedule_relationship"],
                trip_assignment_type=trip_assignment_type,
                trip_is_trip_valid=trip_is_trip_valid,
                trip_is_route_valid=trip_is_route_valid,
                trip_scheduled_start_stop_id=match_inputs["scheduled_start_stop_id"],
                trip_scheduled_end_stop_id=match_inputs["scheduled_end_stop_id"],
                trip_scheduled_start_time=match_inputs["scheduled_start_time"],
                trip_scheduled_end_time=match_inputs["scheduled_end_time"],
                vehicle_id=str(record["vehicle_id"]),
                vehicle_label=record.get("vehicle_label"),
                vehicle_license_plate=record.get("vehicle_license_plate"),
                vehicle_wheelchair_accessible=str(record.get("vehicle_wheelchair_accessible", "NO_VALUE")),
                timestamp=record["timestamp"],
                latitude=float(record["latitude"]),
                longitude=float(record["longitude"]),
                current_stop_sequence=current_stop_sequence,
                current_status=str(record.get("current_status", "IN_TRANSIT_TO")),
                congestion_level=str(record.get("congestion_level", "UNKNOWN_CONGESTION_LEVEL")),
                is_active_on_create=vehicle_is_active_on_create,
            )

            if (
                matched_trip_id is not None
                and matched_assignment_type in (
                    AssignmentType.MATCHED_BY_START_STOP,
                    AssignmentType.MATCHED_BY_INTERMEDIATE_STOPS,
                )
            ):
                await self._caching_service.put_trip_id(derived_trip_id, matched_trip_id)

        vehicles_to_delete = {
            vehicle_id for vehicle_id, vehicle in existing_vehicles.items()
            if vehicle.data_source_id == source_id
            and vehicle_id not in persisted_vehicle_uuids
            and vehicle_id not in policy_based_deletes
        } if not is_differential_updates else set()

        if vehicles_to_delete:
            await realtime_repository.delete_vehicles_for_data_source_by_ids(
                source_id,
                list(vehicles_to_delete),
            )
            
            stats_deleted += len(vehicles_to_delete)

        deleted_vehicle_ids: set[uuid.UUID] = set(vehicles_to_delete)

        if policy_based_deletes:
            await realtime_repository.delete_vehicles_for_data_source_by_ids(
                source_id,
                list(policy_based_deletes),
            )
            
            stats_deleted += len(policy_based_deletes)
            deleted_vehicle_ids.update(policy_based_deletes)

        for vehicle_id in deleted_vehicle_ids:
            deleted_vehicle = existing_vehicles.get(vehicle_id)
            original_trip_id = getattr(getattr(deleted_vehicle, "trip", None), "original_trip_id", None)
            if original_trip_id:
                await self._caching_service.pop_trip_id(original_trip_id)

        logger.info(
            f"[{self.get_adapter_type()}] Vehicle-position import completed for '{source_name}': "
            f"fetched={len(records)}, created={stats_created}, updated={stats_updated}, deleted={stats_deleted}"
        )

        return {
            "added": stats_created,
            "updated": stats_updated,
            "deleted": stats_deleted,
        }
