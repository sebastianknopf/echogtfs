from __future__ import annotations

from datetime import datetime
import logging
import uuid
from typing import Any

from echogtfs.enum.gtfsrt import AssignmentType
from echogtfs.enum.system import IncorrectStopIdHandling, InvalidReferencePolicy
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.matching.matching_service import MatchingService

logger = logging.getLogger("uvicorn")

from .base import RealtimeProcessingServiceBase
from .stop_event_propagation_service import StopEventPropagationService


class TripUpdateProcessingService(RealtimeProcessingServiceBase):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._stop_event_propagation_service = StopEventPropagationService()


    async def sync_records(
        self,
        repository: SystemRepositoryInterface,
        realtime_repository: RealtimeRepositoryInterface,
        gtfs_repository: GtfsRepositoryInterface,
        source_id: int,
        source_name: str,
        records: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Synchronize trip-update records into the database."""
        policy = await repository.get_data_source_invalid_reference_policy(source_id)
        if isinstance(policy, str):
            policy = InvalidReferencePolicy(policy)

        is_differential_updates = await repository.get_data_source_is_differential_updates(source_id)

        logger.info(
            f"[{self.get_adapter_type()}] Synchronizing trip-update records from '{source_name}' "
            f"(policy: {policy.value})"
        )

        await self._identifier_mapping_service.initialize(repository, source_id)

        mapping_count = self._identifier_mapping_service.get_loaded_mapping_count()
        if mapping_count > 0:
            logger.info(
                f"[{self.get_adapter_type()}] Loaded {mapping_count} mapping entries"
            )

        treat_unexpected_stop_as_added_stop = bool(
            self.config.get("treat_unexpected_stop_as_added_stop", False)
        )
        
        treat_missing_stop_as_canceled_stop = bool(
            self.config.get("treat_missing_stop_as_canceled_stop", False)
        )

        incorrect_stop_id_handling = IncorrectStopIdHandling(
            str(
                self.config.get(
                    "incorrect_stop_id_handling",
                    IncorrectStopIdHandling.IGNORE.value,
                )
            )
        )

        gtfs_entities = await self._load_gtfs_entities(gtfs_repository)
        nominal_trip_ids = gtfs_entities.get("trip", set())
        if self._matching_service is None:
            self._matching_service = MatchingService(gtfs_repository, self._caching_service)

        existing_trips = {
            trip.id: trip
            for trip in await realtime_repository.list_trips_for_data_source(source_id)
        }

        existing_trip_ids = set(existing_trips.keys())

        incoming_trip_reference_ids = {
            str(record.get("trip_id") or "")
            for record in records
            if record.get("trip_id")
        }

        existing_trip_uuid_by_trip_id = {
            str(trip.trip_id): trip.id
            for trip in await realtime_repository.list_trips_by_trip_ids(
                list(incoming_trip_reference_ids)
            )
        }

        incoming_trip_ids = {
            existing_trip_uuid_by_trip_id.get(
                str(record.get("trip_id") or ""),
                self._record_uuid(record, source_name, fallback_key="trip_id", kind="Trip-update"),
            )
            for record in records
        }

        existing_trip_ids.update(existing_trip_uuid_by_trip_id.values())

        if incoming_trip_ids:
            trips_by_id = {
                trip.id: trip
                for trip in await realtime_repository.list_trips_by_ids(list(incoming_trip_ids))
            }

            for trip_id, trip in trips_by_id.items():
                if trip_id not in existing_trips:
                    existing_trips[trip_id] = trip
                    existing_trip_ids.add(trip_id)

        stats_created = 0
        stats_updated = 0
        stats_deleted = 0
        policy_based_deletes: set[uuid.UUID] = set()
        processed_trip_uuids: set[uuid.UUID] = set()

        for record in records:
            is_complete_stop_sequence = bool(record.get("is_complete_stop_sequence", True))
            schedule_relationship = str(record.get("schedule_relationship", "SCHEDULED") or "SCHEDULED").upper()

            mapped_trip = self._identifier_mapping_service.apply_mapping(
                {
                    "route_id": record.get("route_id"),
                }
            )
            
            mapped_route_id = str(mapped_trip.get("route_id") or "")
            route_is_valid = bool(mapped_route_id) and mapped_route_id in gtfs_entities.get("route", set())
            is_new_trip = schedule_relationship == "NEW"

            stop_events = []
            has_invalid_stop_reference = False
            for event in record.get("stop_events", []):
                mapped_event = dict(event)
                mapped_stop = self._identifier_mapping_service.apply_mapping(
                    {
                        "stop_id": mapped_event.get("stop_id"),
                    }
                )
                
                mapped_event["stop_id"] = mapped_stop.get("stop_id")
                mapped_stop_id = str(mapped_event.get("stop_id") or "")
                stop_is_valid = bool(mapped_stop_id) and mapped_stop_id in gtfs_entities.get("stop", set())
                if not stop_is_valid:
                    has_invalid_stop_reference = True

                mapped_event["is_valid"] = bool(mapped_event.get("is_valid", True)) and stop_is_valid
                mapped_event["original_stop_id"] = mapped_event.get("stop_id")
                mapped_event["is_implied_schedule_relationship"] = False

                stop_events.append(mapped_event)

            derived_trip_id = str(record["trip_id"])
            original_trip_id = derived_trip_id
            resolved_trip_id = derived_trip_id
            assignment_type = AssignmentType.DIRECT_BY_ID.value
            trip_reference_is_valid = True if is_new_trip else derived_trip_id in nominal_trip_ids
            matched_trip_id: str | None = None
            matched_assignment_type: AssignmentType | None = None

            mapped_match_start_stop = self._identifier_mapping_service.apply_mapping(
                {
                    "stop_id": record.get("scheduled_start_stop_id"),
                }
            )
            
            mapped_match_end_stop = self._identifier_mapping_service.apply_mapping(
                {
                    "stop_id": record.get("scheduled_end_stop_id"),
                }
            )

            scheduled_start_time = self._coerce_datetime(record.get("scheduled_start_time"))
            scheduled_end_time = self._coerce_datetime(record.get("scheduled_end_time"))
            scheduled_start_stop_id = mapped_match_start_stop.get("stop_id")
            scheduled_end_stop_id = mapped_match_end_stop.get("stop_id")
            scheduled_intermediate_stops: list[tuple[str, datetime]] = []

            intermediate_candidates = record.get("scheduled_intermediate_stops")
            if isinstance(intermediate_candidates, list):
                for candidate in intermediate_candidates:
                    if not isinstance(candidate, tuple) or len(candidate) != 2:
                        continue

                    candidate_stop_id, candidate_time = candidate
                    mapped_intermediate_stop = self._identifier_mapping_service.apply_mapping(
                        {
                            "stop_id": candidate_stop_id,
                        }
                    )
                    
                    mapped_stop_id = mapped_intermediate_stop.get("stop_id")
                    coerced_time = self._coerce_datetime(candidate_time)

                    if mapped_stop_id is None or coerced_time is None:
                        continue

                    scheduled_intermediate_stops.append((str(mapped_stop_id), coerced_time))

            if not is_new_trip and not trip_reference_is_valid:
                matched_trip_id, matched_assignment_type = await self._matching_service.match(
                    trip_id=derived_trip_id,
                    route_id=str(mapped_trip.get("route_id") or "") or None,
                    operation_day_date=self._parse_operation_day(record.get("start_date")),
                    scheduled_start_time=scheduled_start_time,
                    scheduled_end_time=scheduled_end_time,
                    scheduled_start_stop_id=(
                        str(scheduled_start_stop_id)
                        if scheduled_start_stop_id is not None
                        else None
                    ),
                    scheduled_end_stop_id=(
                        str(scheduled_end_stop_id)
                        if scheduled_end_stop_id is not None
                        else None
                    ),
                    scheduled_intermediate_stops=scheduled_intermediate_stops,
                    is_complete_stop_sequence=is_complete_stop_sequence,
                    intermediate_stop_sample_size=max(3, len(record.get("stop_events") or [])),
                )

                if matched_trip_id is not None:
                    resolved_trip_id = matched_trip_id
                    assignment_type = matched_assignment_type.value

                    trip_reference_is_valid = True

                    await realtime_repository.delete_trips_by_trip_ids([original_trip_id])
                else:
                    assignment_type = matched_assignment_type.value

            persisted_trip_uuid = existing_trip_uuid_by_trip_id.get(str(resolved_trip_id))
            if persisted_trip_uuid is None:
                persisted_trip_uuid = self._make_unique_id(resolved_trip_id, source_name)

            existing_trip = persisted_trip_uuid in existing_trip_ids
            existing_trip_model = existing_trips.get(persisted_trip_uuid)
            persist_is_complete_stop_sequence = is_complete_stop_sequence

            if not is_new_trip:
                if is_complete_stop_sequence:
                    nominal_trip = await gtfs_repository.get_gtfs_trip_with_stop_times(resolved_trip_id)
                    nominal_stop_times = list(nominal_trip.stop_times) if nominal_trip is not None else []
                    stop_events = self._stop_event_propagation_service._propagate_trip_update_stop_events(
                        stop_events,
                        nominal_stop_times,
                        treat_unexpected_stop_as_added_stop=treat_unexpected_stop_as_added_stop,
                        treat_missing_stop_as_canceled_stop=treat_missing_stop_as_canceled_stop,
                        is_complete_stop_sequence=is_complete_stop_sequence,
                        incorrect_stop_id_handling=incorrect_stop_id_handling,
                    )

                    for idx, event in enumerate(stop_events, start=1):
                        event["stop_sequence"] = str(idx)
                elif existing_trip_model is not None and existing_trip_model.is_complete_stop_sequence:
                    # Incremental update on top of an already-complete sequence: merge instead of replacing.
                    existing_stop_events = await realtime_repository.list_stop_events_for_trip(
                        existing_trip_model.trip_id
                    )
                    
                    stop_events = self._stop_event_propagation_service._merge_incremental_stop_events(
                        [self._stop_event_propagation_service._stop_event_to_dict(event) for event in existing_stop_events],
                        stop_events,
                    )
                    
                    persist_is_complete_stop_sequence = True

                    for idx, event in enumerate(stop_events, start=1):
                        event["stop_sequence"] = str(idx)
                else:
                    # No prior complete sequence exists yet: a stop's true position within the
                    # full trip is unknown, so stop_sequence is intentionally left blank.
                    for event in stop_events:
                        event["stop_sequence"] = ""

            # An incremental update only carries partial stop data and must never overwrite the
            # trip's known scheduled start/end anchors; keep them for an already-complete trip,
            # or leave them unset when the trip has never had a complete stop sequence.
            if is_complete_stop_sequence:
                persist_scheduled_start_time = scheduled_start_time
                persist_scheduled_end_time = scheduled_end_time
                persist_scheduled_start_stop_id = scheduled_start_stop_id
                persist_scheduled_end_stop_id = scheduled_end_stop_id
            elif existing_trip_model is not None and existing_trip_model.is_complete_stop_sequence:
                persist_scheduled_start_time = existing_trip_model.scheduled_start_time
                persist_scheduled_end_time = existing_trip_model.scheduled_end_time
                persist_scheduled_start_stop_id = existing_trip_model.scheduled_start_stop_id
                persist_scheduled_end_stop_id = existing_trip_model.scheduled_end_stop_id
            else:
                persist_scheduled_start_time = None
                persist_scheduled_end_time = None
                persist_scheduled_start_stop_id = None
                persist_scheduled_end_stop_id = None

            # start_time is derived from the first stop of a full update; an incremental update's
            # first delivered stop is not necessarily the trip's actual start, so it must not
            # overwrite an already-known start_time, and stays unset for a brand-new trip.
            if is_complete_stop_sequence:
                persist_start_time = str(record["start_time"])
            elif existing_trip_model is not None:
                persist_start_time = existing_trip_model.start_time
            else:
                persist_start_time = None

            has_invalid_stop_reference = any(not bool(event.get("is_valid", True)) for event in stop_events)

            has_invalid_reference = (not route_is_valid) or has_invalid_stop_reference or (not trip_reference_is_valid)

            should_skip_trip = False
            should_deactivate_trip = False
            stop_events_to_persist = stop_events
            route_id_to_persist = mapped_route_id

            if has_invalid_reference:
                if policy == InvalidReferencePolicy.DISCARD_ENTIRE_OBJECT:
                    should_skip_trip = True
                    if persisted_trip_uuid in existing_trip_ids:
                        policy_based_deletes.add(persisted_trip_uuid)

                elif policy in (
                    InvalidReferencePolicy.DISCARD_INVALID,
                    InvalidReferencePolicy.DISCARD_INVALID_ELEMENTS,
                ):
                    stop_events_to_persist = [event for event in stop_events if bool(event.get("is_valid"))]
                    if not route_is_valid:
                        route_id_to_persist = ""

                    has_any_valid_reference = (
                        trip_reference_is_valid
                        or bool(route_id_to_persist)
                        or bool(stop_events_to_persist)
                    )
                    if (
                        not existing_trip
                        and ((not trip_reference_is_valid) or (not has_any_valid_reference))
                    ):
                        should_deactivate_trip = True

                elif policy == InvalidReferencePolicy.KEEP_OBJECT_DISABLED:
                    should_deactivate_trip = not existing_trip

            if should_skip_trip:
                continue

            if existing_trip:
                is_active_on_create = bool(existing_trips[persisted_trip_uuid].is_active)
            else:
                is_active_on_create = bool(record.get("is_active", True))
                if should_deactivate_trip:
                    is_active_on_create = False

            trip_is_trip_valid = trip_reference_is_valid
            trip_is_route_valid = route_is_valid

            if existing_trip:
                stats_updated += 1
            else:
                stats_created += 1
                existing_trip_ids.add(persisted_trip_uuid)

            existing_trip_uuid_by_trip_id[str(resolved_trip_id)] = persisted_trip_uuid
            processed_trip_uuids.add(persisted_trip_uuid)

            await realtime_repository.update_trip_update_from_sync(
                trip_uuid=persisted_trip_uuid,
                source_id=source_id,
                source_name=source_name,
                trip_id=resolved_trip_id,
                start_time=persist_start_time,
                start_date=str(record["start_date"]),
                route_id=route_id_to_persist,
                schedule_relationship=str(record.get("schedule_relationship", "SCHEDULED")),
                assignment_type=assignment_type,
                is_active_on_create=is_active_on_create,
                is_trip_valid=trip_is_trip_valid,
                is_route_valid=trip_is_route_valid,
                stop_events=stop_events_to_persist,
                original_trip_id=original_trip_id,
                scheduled_start_stop_id=(
                    str(persist_scheduled_start_stop_id)
                    if persist_scheduled_start_stop_id is not None
                    else None
                ),
                scheduled_end_stop_id=(
                    str(persist_scheduled_end_stop_id)
                    if persist_scheduled_end_stop_id is not None
                    else None
                ),
                scheduled_start_time=persist_scheduled_start_time,
                scheduled_end_time=persist_scheduled_end_time,
                is_complete_stop_sequence=persist_is_complete_stop_sequence,
            )

            if (
                matched_trip_id is not None
                and matched_assignment_type in (
                    AssignmentType.MATCHED_BY_START_STOP,
                    AssignmentType.MATCHED_BY_INTERMEDIATE_STOPS,
                )
            ):
                await self._caching_service.put_trip_id(derived_trip_id, matched_trip_id)

        trips_to_delete = {
            trip_id: trip
            for trip_id, trip in existing_trips.items()
            if trip.data_source_id == source_id
            and trip_id not in processed_trip_uuids
            and trip_id not in policy_based_deletes
        } if not is_differential_updates else {}

        if trips_to_delete:
            await realtime_repository.delete_trips_for_data_source_by_ids(
                source_id,
                list(trips_to_delete.keys()),
            )

            for id, trip in trips_to_delete.items():
                await self._caching_service.pop_trip_id(trip.original_trip_id)

            stats_deleted += len(trips_to_delete)

        if policy_based_deletes:
            await realtime_repository.delete_trips_for_data_source_by_ids(
                source_id,
                list(policy_based_deletes),
            )

            for trip_id in policy_based_deletes:
                await self._caching_service.pop_trip_id(trip_id)

            stats_deleted += len(policy_based_deletes)

        logger.info(
            f"[{self.get_adapter_type()}] Trip-update import completed for '{source_name}': "
            f"fetched={len(records)}, created={stats_created}, updated={stats_updated}, deleted={stats_deleted}"
        )

        return {
            "added": stats_created,
            "updated": stats_updated,
            "deleted": stats_deleted,
        }
