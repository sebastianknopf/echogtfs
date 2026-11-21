# Transformer Return Model

## Transformer Contract

Transformer output is returned by `DatasourceBase._fetch_records`. `DatasourceBase` hands the payload to `RealtimeProcessingDispatcherService`, which normalizes the envelope and dispatches the records to the entity-specific processing service.

A transformer must return this envelope shape:

```python
{
    "record_type": "service_alerts" | "trip_updates" | "vehicle_positions",
    "records": [
        # list[dict[str, Any]]
    ],
}
```

## Sync Pipeline

The realtime processing layer expects dictionary records per `record_type`. These dictionaries are processed in this order:

Implementation notes for the concrete transformers are collected in [transformers/README.md](transformers/README.md). The most relevant notes are:

- [transformers/efa_json_service_alerts_transformer.md](transformers/efa_json_service_alerts_transformer.md)
- [transformers/gtfsrt_service_alerts_transformer.md](transformers/gtfsrt_service_alerts_transformer.md)
- [transformers/sirisx_service_alerts_transformer.md](transformers/sirisx_service_alerts_transformer.md)
- [transformers/sirisx_swiss_service_alerts_transformer.md](transformers/sirisx_swiss_service_alerts_transformer.md)
- [transformers/siriet_trip_updates_transformer.md](transformers/siriet_trip_updates_transformer.md)
- [transformers/sirivm_vehicle_positions_transformer.md](transformers/sirivm_vehicle_positions_transformer.md)

1. Fetch records from transformer.
2. Normalize payload into (record_type, records).
3. Dispatch to the matching entity-specific processing service.
4. Apply identifier mapping and enrichment where supported.
5. For trip-related records, run `MatchingService` only when the derived `trip_id` is not in nominal GTFS trip IDs.
6. For Trip Updates, reconcile and propagate stop events through `StopEventPropagationService`.
7. Upsert into realtime tables.

Only fields listed below are consumed by the realtime processing services and/or `RealtimeRepository` for each record type.

## Deleted Records

A record with `is_deleted = True` is a deletion request. Before normal processing, each realtime processing service splits these records from the rest and handles them as follows:

- The entity is deleted by its ID (for trip updates, also by the stored trip reference) through the data-source-scoped repository delete, within the running sync transaction.
- The result of the deletion is ignored. An entity that no longer exists (for example after cleanup or transformer filtering) is neither an error nor a reason to stop the run.
- The record is not validated, mapped, enriched, matched, or persisted. Only `id` is required (`trip_id` or `vehicle_id` serve as fallback for trip updates and vehicle positions).
- The same entity is not deleted a second time by the deletion of entities missing from the feed.

The following structures describe the internal data model, which can be returned by a transformer to the data source implementation for further processing (mapping, matching, persistence).

## record_type service_alerts

Allowed data model:

```python
{
    "id": str,
    "is_deleted": bool,
    "cause": str,
    "effect": str,
    "severity_level": str,
    "is_active": bool,
    "is_closing_alert": bool,
    "translations": [
        {
            "language": str,
            "header_text": str | None,
            "description_text": str | None,
            "url": str | None,
        }
    ],
    "active_periods": [
        {
            "period_type": str,
            "start_time": int | None,
            "end_time": int | None,
        }
    ],
    "informed_entities": [
        {
            "agency_id": str | None,
            "route_id": str | None,
            "route_type": int | None,
            "stop_id": str | None,
            "trip_id": str | None,
            "direction_id": int | None,
            "is_agency_valid": bool,
            "is_route_valid": bool,
            "is_stop_valid": bool,
            "is_trip_valid": bool,
        }
    ],
}
```

The corresponding realtime processing service also writes these internal fields before persistence:

- source: overwritten with the current data source name.
- data_source_id: overwritten with the current data source id.
- informed_entities[*].original_agency_id / mapped_agency_id, original_route_id / mapped_route_id, original_stop_id / mapped_stop_id, original_trip_id / mapped_trip_id: not supplied by the transformer; derived by `ServiceAlertProcessingService` (see below).

Processed top-level fields:

- id: required.
- is_deleted: optional, default False.
- cause: required.
- effect: required.
- severity_level: required.
- is_active: optional, used only for create path, default True.
- is_closing_alert: optional, default False.
- translations: optional list, default [].
- active_periods: optional list, default [].
- informed_entities: optional list, default [].

Processed translations[*] fields:

- language: required by persistence model.
- header_text: optional.
- description_text: optional.
- url: optional.

Processed active_periods[*] fields:

- period_type: optional.
- start_time: optional.
- end_time: optional.

Processed informed_entities[*] fields:

- agency_id: optional.
- route_id: optional.
- route_type: optional.
- stop_id: optional.
- trip_id: optional.
- direction_id: optional.
- is_agency_valid: optional input; combined with computed agency-reference validity.
- is_route_valid: optional input; combined with computed route-reference validity.
- is_stop_valid: optional input; combined with computed stop-reference validity.
- is_trip_valid: optional input; combined with computed trip-reference validity.

`ServiceAlertProcessingService` derives and persists three identifier fields per reference type (agency, route, stop, trip), all nullable:

- original_{type}_id: set once, before mapping, to the raw/transmitted `{type}_id`.
- mapped_{type}_id: initialized to the same raw value, then updated to the applied mapping result when a mapping rule matches `{type}_id`. `trip_id` is never mapped, so `mapped_trip_id` always equals `original_trip_id`.
- `{type}_id`: continues to hold the working/mapped value used for validity checks, policy cleanup and persistence, as before this derivation was introduced.

Aggregate service-alert entity validity is computed internally from all four per-reference flags, using `mapped_{type}_id` (falling back to `{type}_id`) to look up nominal GTFS validity.

Invalid-reference policy effects for service_alerts:

- `discard_entire_object`: skip the full alert and delete an existing synced alert with the same ID.
- `discard_invalid`: keep only informed entities where all four validity flags evaluate to true.
- `discard_invalid_elements`: clear invalid `agency_id`, `route_id`, and `stop_id` fields (and their corresponding `mapped_{type}_id`) inside an entity, then keep only entities that still have at least one valid reference.
- `keep_object_disabled`: keep the alert but force `is_active` to false for new alerts.
- Any alert with no remaining informed entities is deactivated.

Mapped fields in service_alerts:

- informed_entities[*].agency_id
- informed_entities[*].route_id
- informed_entities[*].stop_id

Not mapped in service_alerts:

- informed_entities[*].trip_id

## record_type trip_updates

For differential source behavior and incremental merge semantics in the sync pipeline, see [differential-incremental.md](differential-incremental.md).

Allowed data model:

```python
{
    "id": str,
    "is_deleted": bool,
    "trip_id": str,
    "start_time": str,
    "start_date": str,
    "route_id": str,
    "schedule_relationship": str,
    "assignment_type": str,
    "is_active": bool,
    "is_trip_valid": bool,
    "is_route_valid": bool,
    "is_complete_stop_sequence": bool,
    "scheduled_start_stop_id": str | None,
    "scheduled_start_time": datetime | None,
    "scheduled_end_stop_id": str | None,
    "scheduled_end_time": datetime | None,
    "scheduled_intermediate_stops": list[tuple[str, datetime]],
    "stop_events": [
        {
            "trip_id": str,
            "stop_id": str,
            "stop_sequence": str,
            "arrival_time": str | datetime,
            "departure_time": str | datetime,
            "scheduled_arrival_time": str | datetime | None,
            "scheduled_departure_time": str | datetime | None,
            "schedule_relationship": str,
            "is_implied_schedule_relationship": bool,
            "is_valid": bool,
        }
    ],
}
```

Processed top-level fields:

- id: optional. If missing, deterministic UUID is built from trip_id.
- is_deleted: optional, default False.
- trip_id: required.
- start_time: required.
- start_date: required.
- route_id: required, mapped before persistence and matching.
- schedule_relationship: optional, default SCHEDULED.
- is_active: optional create-only value, default True.
- is_trip_valid: optional, default True.
- is_route_valid: optional, default True.
- is_complete_stop_sequence: optional boolean, default False.
- scheduled_start_stop_id: nullable, mapped and passed to matching when trip_id is non-nominal.
- scheduled_start_time: nullable, coerced to datetime and passed to matching when trip_id is non-nominal.
- scheduled_end_stop_id: nullable, mapped and passed to matching when trip_id is non-nominal.
- scheduled_end_time: nullable, coerced to datetime and passed to matching when trip_id is non-nominal.
- scheduled_intermediate_stops: optional list of `(stop_id, datetime)` tuples for additional scheduled anchors.
- stop_events: optional list, default [].

`TripUpdateProcessingService` derives and persists `original_trip_id` and `mapped_trip_id` (both non-nullable), not supplied by the transformer:

- original_trip_id: set once, before matching, to the raw/transmitted `trip_id`.
- mapped_trip_id: initialized to the same raw value. `trip_id` is never mapped by `IdentifierMappingService`, so `mapped_trip_id` always equals `original_trip_id`.
- trip_id: continues to hold the working value used for validity checks and persistence; it may later be replaced with a matched trip ID (see "Assignment behavior for trip_updates" below), which does not affect `mapped_trip_id`/`original_trip_id`.

Processed stop_events[*] fields:

- stop_id: consumed and mapped before persistence.
- stop_sequence: passed to persistence model.
- arrival_time: passed to persistence model.
- departure_time: passed to persistence model.
- scheduled_arrival_time: optional planned arrival time supplied by the transformer; passed to the persistence model and available for stop-event matching/propagation. See more about the matching / propagation [here](stop-propagation.md)
- scheduled_departure_time: optional planned departure time supplied by the transformer; passed to the persistence model and used as a tie-breaker when repeated stop occurrences require disambiguation.
- schedule_relationship: optional, default SCHEDULED in persistence layer.
- is_implied_schedule_relationship: Indicates whether the schedule relationship was implied based on settings, optional, default False.
- is_valid: optional, default True in persistence layer.
- trip_id: optional input but explicitly removed and replaced with resolved trip_id before persistence.

`TripUpdateProcessingService` and `StopEventPropagationService` mutate each stop event during processing:

- `original_stop_id` is derived first, before mapping, as the raw/transmitted `stop_id`.
- `stop_id` is replaced with the mapped stop ID.
- `mapped_stop_id` is derived from the (already mapped) `stop_id`, so it stays in sync with `stop_id` through any later policy-based cleanup.
- `is_implied_schedule_relationship` is set to true only for stop events implied by datasource flags (`ADDED` via `treat_unexpected_stop_as_added_stop`, `SKIPPED` via `treat_missing_stop_as_canceled_stop`).
- `is_valid` is forced to `input_is_valid and stop_id_in_nominal_gtfs`.

Derived matching inputs for trip_updates:

- scheduled_start_time: taken from transformer field scheduled_start_time and coerced to datetime, or None.
- scheduled_end_time: taken from transformer field scheduled_end_time and coerced to datetime, or None.
- scheduled_start_stop_id: taken from transformer field scheduled_start_stop_id, mapped via stop mapping, or None.
- scheduled_end_stop_id: taken from transformer field scheduled_end_stop_id, mapped via stop mapping, or None.
- scheduled_intermediate_stops: optional mapped list of `(stop_id, datetime)` tuples used only as fallback matching anchors.

Intermediate fallback matching for trip_updates:

- Used only when both `scheduled_start_time` and `scheduled_end_time` are `None`.
- Each fallback anchor compares mapped stop IDs on GlobalId level 3.
- Matching is done against `gtfs_stop_times.departure_time` with a bias of +/- 60 seconds.

Assignment behavior for trip_updates:

- If trip_id is nominal GTFS trip ID: assignment_type becomes DIRECT_BY_ID.
- If trip_id is not nominal and match succeeds: assignment_type becomes MATCHED_BY_START_STOP and trip_id is replaced by matched ID.
- If trip_id is not nominal and match fails: assignment_type becomes NO_MATCH_GENERAL.

Invalid-reference policy effects for trip_updates:

- An invalid reference means at least one of these is true:
    - `route_id` is not contained in nominal GTFS route IDs after mapping.
    - any `stop_events[*].stop_id` is not contained in nominal GTFS stop IDs after mapping.
    - `trip_id` is neither a nominal GTFS trip ID nor successfully matched.
- `trip.is_trip_valid` persisted via `update_trip_update_from_sync(..., is_trip_valid=...)` becomes false when the trip reference is invalid.
- `trip.is_route_valid` persisted via `update_trip_update_from_sync(..., is_route_valid=...)` becomes false when the route reference is invalid.
- `discard_entire_object`: skip the full trip update and delete an existing synced trip with the same ID.
- `discard_invalid` and `discard_invalid_elements`:
    - remove invalid stop events from `stop_events`.
    - clear `route_id` to an empty string when the mapped route is invalid.
    - deactivate the trip when `trip_id` is still unresolved or when no valid references remain.
- `keep_object_disabled`: keep the trip update but force `is_active` to false on create.

## record_type vehicle_positions

Allowed data model:

```python
{
    "id": str,
    "is_deleted": bool,
    "trip": {
        "trip_id": str,
        "start_time": str,
        "start_date": str,
        "route_id": str,
        "schedule_relationship": str,
        "assignment_type": str,
        "is_active": bool,
        "is_trip_valid": bool,
        "is_route_valid": bool,
        "is_complete_stop_sequence": bool,
        "scheduled_start_stop_id": str | None,
        "scheduled_start_time": datetime | None,
        "scheduled_end_stop_id": str | None,
        "scheduled_end_time": datetime | None,
        "scheduled_intermediate_stops": list[tuple[str, datetime]],
    },
    "vehicle_id": str,
    "vehicle_label": str | None,
    "vehicle_license_plate": str | None,
    "vehicle_wheelchair_accessible": str,
    "timestamp": str | datetime,
    "latitude": float | int,
    "longitude": float | int,
    "current_status": str,
    "congestion_level": str,
    "is_active": bool,
    "stop_id": str | None,
}
```

Processed top-level fields:

- id: optional. If missing, deterministic UUID is built from vehicle_id.
- is_deleted: optional, default False.
- vehicle_id: required.
- vehicle_label: optional.
- vehicle_license_plate: optional.
- vehicle_wheelchair_accessible: optional, default NO_VALUE.
- timestamp: required.
- latitude: required.
- longitude: required.
- current_status: optional, default IN_TRANSIT_TO.
- congestion_level: optional, default UNKNOWN_CONGESTION_LEVEL.
- is_active: optional create-only value for vehicle, default True.
- stop_id: optional. Current stop of the vehicle; validated against nominal GTFS stop IDs and persisted as nullable `stop_id`.

`VehiclePositionProcessingService` derives and persists `trip.original_trip_id` and `trip.mapped_trip_id` (both non-nullable), not supplied by the transformer, following the same rule as for trip_updates: `trip.original_trip_id` is set once to the raw/transmitted `trip.trip_id`, and `trip.mapped_trip_id` is initialized to the same value since `trip_id` is never mapped by `IdentifierMappingService`.

Trip payload sources for vehicle_positions:

- Required nested trip object only: trip.trip_id, trip.start_time, trip.start_date, trip.route_id, trip.schedule_relationship, trip.is_active, trip.is_trip_valid, trip.is_route_valid, trip.scheduled_start_stop_id, trip.scheduled_start_time, trip.scheduled_end_stop_id, trip.scheduled_end_time.

Trip payload processing rules:

- trip object is required; records without a valid trip object are discarded.
- trip_id is required inside trip object.
- start_time defaults to empty string when missing.
- start_date defaults to empty string when missing.
- route_id defaults to empty string when missing, then mapped.
- schedule_relationship defaults to SCHEDULED when missing.
- nested `trip.assignment_type` is read into the normalized trip payload but not persisted unchanged.
- trip is_active_on_create defaults to True.
- trip is_trip_valid defaults to True.
- trip is_route_valid defaults to True.
- mapped `route_id` replaces the original route ID in the normalized trip payload.
- trip.scheduled_start_stop_id, trip.scheduled_start_time, trip.scheduled_end_stop_id, and trip.scheduled_end_time are nullable, passed to matching and persisted in the trip descriptor (stop IDs after mapping).
- trip.scheduled_intermediate_stops is an optional list of `(stop_id, datetime)` tuples for additional scheduled anchors.
- trip.is_complete_stop_sequence is an optional boolean, default True. If true, matching first uses the start/end anchors; otherwise only the intermediate stops are used. A flat top-level `is_complete_stop_sequence` is accepted as fallback.

Derived matching inputs for vehicle_positions:

- scheduled_start_time: taken from transformer field trip.scheduled_start_time and coerced to datetime, or None.
- scheduled_end_time: taken from transformer field trip.scheduled_end_time and coerced to datetime, or None.
- scheduled_start_stop_id: taken from transformer field trip.scheduled_start_stop_id, mapped via stop mapping, or None.
- scheduled_end_stop_id: taken from transformer field trip.scheduled_end_stop_id, mapped via stop mapping, or None.
- scheduled_intermediate_stops: optional mapped list of `(stop_id, datetime)` tuples from the trip payload, or the flat vehicle payload as fallback.
- The matching cycle (cached ID, start/end anchors, intermediate-stop fallback, assignment types) is the same as for trip_updates.

Intermediate fallback matching for vehicle_positions:

- Used only when both `scheduled_start_time` and `scheduled_end_time` are `None`.
- Each fallback anchor compares mapped stop IDs on GlobalId level 3.
- Matching is done against `gtfs_stop_times.departure_time` with a bias of +/- 60 seconds.

Assignment behavior for vehicle_positions:

- If trip_id is nominal GTFS trip ID: trip_assignment_type becomes DIRECT_BY_ID.
- If trip_id is not nominal and match succeeds: the trip assignment type becomes MATCHED_BY_CURRENT_STOP and trip_id is replaced by matched ID.
- If trip_id is not nominal and match fails: the trip assignment type becomes NO_MATCH_GENERAL.

Invalid-reference policy effects for vehicle_positions:

- An invalid reference means at least one of these is true:
    - `trip.route_id` is not contained in nominal GTFS route IDs after mapping.
    - optional `stop_id` is present but not contained in nominal GTFS stop IDs.
    - `trip_id` is neither a nominal GTFS trip ID nor successfully matched.
- Persisted `trip_is_trip_valid` becomes false when the trip reference is invalid.
- Persisted `trip_is_route_valid` becomes false when the route reference is invalid.
- A vehicle position is valid when its trip descriptor is valid (`is_trip_valid` and `is_route_valid`) and its stop reference is valid. An invalid optional `stop_id` additionally affects the invalid-reference policy.
- Any invalid reference (trip, route or stop) creates a new vehicle position with `is_active` false, regardless of the policy, except `discard_entire_object`, which skips the record.
- `discard_entire_object`: skip the full vehicle position and delete an existing synced vehicle with the same ID.
- `discard_invalid` and `discard_invalid_elements`:
    - clear trip `route_id` to an empty string when the mapped route is invalid.
    - deactivate the vehicle when `trip_id` is still unresolved or when no valid references remain.
- `keep_object_disabled`: keep the vehicle position but force vehicle `is_active` to false on create.
