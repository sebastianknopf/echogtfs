# Transformer Return Model

## Relevant Files

- `backend/src/echogtfs/datasources/base.py`
- `backend/src/echogtfs/services/database/realtime_repository.py`
- `backend/src/echogtfs/services/mapping/identifier_mapping_service.py`

## Transformer Contract

Transformer output is consumed by DatasourceBase._fetch_records and normalized by DatasourceBase._normalize_fetched_payload.

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

DatasourceBase expects dictionary records per record_type. These dictionaries are processed in this order:

1. Fetch records from transformer.
2. Normalize payload into (record_type, records).
3. Initialize mapping/enrichment/matching dependencies.
4. Apply identifier mapping where supported.
5. For trip-related records, run matching only when derived trip_id is not in nominal GTFS trip IDs.
6. Upsert into realtime tables.

Only fields listed below are consumed by DatasourceBase and/or RealtimeRepository for each record type.

## record_type service_alerts

Allowed data model:

```python
{
    "id": str,
    "cause": str,
    "effect": str,
    "severity_level": str,
    "is_active": bool,
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
            "is_valid": bool,
        }
    ],
}
```

DatasourceBase also writes these internal fields before persistence:

- source: overwritten with the current data source name.
- data_source_id: overwritten with the current data source id.

Processed top-level fields:

- id: required.
- cause: required.
- effect: required.
- severity_level: required.
- is_active: optional, used only for create path, default True.
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
- is_valid: optional input; may be set or overridden by invalid-reference policy flow.

Invalid-reference policy effects for service_alerts:

- `discard_entire_object`: skip the full alert and delete an existing synced alert with the same ID.
- `discard_invalid`: keep only informed entities where `is_valid` is true.
- `discard_invalid_elements`: clear invalid `agency_id`, `route_id`, and `stop_id` fields inside an entity, then keep only entities that still have at least one valid reference.
- `keep_object_disabled`: keep the alert but force `is_active` to false for new alerts.
- Any alert with no remaining informed entities is deactivated.

Mapped fields in service_alerts:

- informed_entities[*].agency_id
- informed_entities[*].route_id
- informed_entities[*].stop_id

Not mapped in service_alerts:

- informed_entities[*].trip_id

## record_type trip_updates

Allowed data model:

```python
{
    "id": str,
    "trip_id": str,
    "start_time": str,
    "start_date": str,
    "route_id": str,
    "schedule_relationship": str,
    "assignment_type": str,
    "is_active": bool,
    "is_valid": bool,
    "stop_events": [
        {
            "trip_id": str,
            "stop_id": str,
            "stop_sequence": str,
            "arrival_time": str | datetime,
            "departure_time": str | datetime,
            "schedule_relationship": str,
            "is_valid": bool,
        }
    ],
}
```

DatasourceBase derives this internal processing state for each trip update:

```python
{
    "trip_uuid": uuid.UUID,
    "resolved_trip_id": str,
    "mapped_route_id": str,
    "route_is_valid": bool,
    "trip_reference_is_valid": bool,
    "has_invalid_stop_reference": bool,
    "scheduled_start_time": datetime | None,
    "scheduled_end_time": datetime | None,
    "scheduled_start_stop_id": str | None,
    "scheduled_end_stop_id": str | None,
    "assignment_type": str,
    "stop_events_to_persist": [
        {
            "trip_id": str,
            "stop_id": str,
            "stop_sequence": str,
            "arrival_time": str | datetime,
            "departure_time": str | datetime,
            "schedule_relationship": str,
            "is_valid": bool,
        }
    ],
}
```

Processed top-level fields:

- id: optional. If missing, deterministic UUID is built from trip_id.
- trip_id: required.
- start_time: required (also used to derive matching input scheduled_start_time).
- start_date: required (also used to derive matching input scheduled_start_time).
- route_id: required, mapped before persistence and matching.
- schedule_relationship: optional, default SCHEDULED.
- is_active: optional create-only value, default True.
- is_valid: optional, default True.
- stop_events: optional list, default [].

Processed stop_events[*] fields:

- stop_id: consumed, mapped before persistence, used for matching start/end stop inputs.
- stop_sequence: passed to persistence model.
- arrival_time: consumed; used as fallback to derive scheduled_end_time from last stop event.
- departure_time: consumed; preferred source to derive scheduled_end_time from last stop event.
- schedule_relationship: optional, default SCHEDULED in persistence layer.
- is_valid: optional, default True in persistence layer.
- trip_id: optional input but explicitly removed and replaced with resolved trip_id before persistence.

DatasourceBase mutates each stop event during processing:

- `stop_id` is replaced with the mapped stop ID.
- `is_valid` is forced to `input_is_valid and stop_id_in_nominal_gtfs`.

Derived matching inputs for trip_updates:

- scheduled_start_time: derived from start_date + start_time via %Y%m%d %H:%M:%S parser.
- scheduled_end_time: derived from last stop event departure_time, or arrival_time fallback, parsed as datetime/ISO string; otherwise None.
- scheduled_start_stop_id: first stop_events[*].stop_id after mapping, or None.
- scheduled_end_stop_id: last stop_events[*].stop_id after mapping, or None.

Assignment behavior for trip_updates:

- If trip_id is nominal GTFS trip ID: assignment_type becomes DIRECT_BY_ID.
- If trip_id is not nominal and match succeeds: assignment_type becomes MATCHED_BY_START_STOP and trip_id is replaced by matched ID.
- If trip_id is not nominal and match fails: assignment_type becomes NO_MATCH_GENERAL.

Invalid-reference policy effects for trip_updates:

- An invalid reference means at least one of these is true:
    - `route_id` is not contained in nominal GTFS route IDs after mapping.
    - any `stop_events[*].stop_id` is not contained in nominal GTFS stop IDs after mapping.
    - `trip_id` is neither a nominal GTFS trip ID nor successfully matched.
- `trip.is_valid` persisted via `update_trip_update_from_sync(..., is_valid=...)` becomes false when any invalid reference exists.
- `discard_entire_object`: skip the full trip update and delete an existing synced trip with the same ID.
- `discard_invalid` and `discard_invalid_elements`:
    - remove invalid stop events from `stop_events`.
    - clear `route_id` to an empty string when the mapped route is invalid.
    - deactivate the trip when `trip_id` is still unresolved or when no valid references remain.
- `keep_object_disabled`: keep the trip update but force `is_active` to false on create.

Fields not consumed from trip_updates:

- top-level assignment_type input is ignored and overwritten by derived assignment_type.

## record_type vehicle_positions

Allowed data model:

```python
{
    "id": str,
    "trip": {
        "trip_id": str,
        "start_time": str,
        "start_date": str,
        "route_id": str,
        "schedule_relationship": str,
        "assignment_type": str,
        "is_active": bool,
        "is_valid": bool,
    },
    "trip_id": str,
    "trip_start_time": str,
    "trip_start_date": str,
    "trip_route_id": str,
    "trip_schedule_relationship": str,
    "trip_assignment_type": str,
    "trip_is_active_on_create": bool,
    "trip_is_valid": bool,
    "vehicle_id": str,
    "vehicle_label": str | None,
    "vehicle_license_plate": str | None,
    "vehicle_wheelchair_accessible": str,
    "timestamp": str | datetime,
    "latitude": float | int,
    "longitude": float | int,
    "current_stop_sequence": int,
    "current_status": str,
    "assignment_type": str,
    "congestion_level": str,
    "is_active": bool,
    "is_valid": bool,
    "stop_id": str,
}
```

DatasourceBase derives this internal processing state for each vehicle position:

```python
{
    "vehicle_uuid": uuid.UUID,
    "trip_uuid": uuid.UUID,
    "resolved_trip_id": str,
    "trip_payload": {
        "trip_id": str,
        "start_time": str,
        "start_date": str,
        "route_id": str,
        "schedule_relationship": str,
        "assignment_type": str,
        "is_active_on_create": bool,
        "is_valid": bool,
    },
    "route_is_valid": bool,
    "stop_reference_is_valid": bool,
    "trip_reference_is_valid": bool,
    "scheduled_start_time": datetime | None,
    "scheduled_end_time": None,
    "scheduled_start_stop_id": str | None,
    "scheduled_end_stop_id": str | None,
    "trip_assignment_type": str,
    "vehicle_assignment_type": str,
}
```

Processed top-level fields:

- id: optional. If missing, deterministic UUID is built from vehicle_id.
- vehicle_id: required.
- vehicle_label: optional.
- vehicle_license_plate: optional.
- vehicle_wheelchair_accessible: optional, default NO_VALUE.
- timestamp: required.
- latitude: required.
- longitude: required.
- current_stop_sequence: optional, default 0.
- current_status: optional, default IN_TRANSIT_TO.
- congestion_level: optional, default UNKNOWN_CONGESTION_LEVEL.
- is_active: optional create-only value for vehicle, default True.
- is_valid: optional value for vehicle, default True.
- stop_id: optional matching hint.

Trip payload sources for vehicle_positions:

- Nested trip object: trip.trip_id, trip.start_time, trip.start_date, trip.route_id, trip.schedule_relationship, trip.is_active, trip.is_valid.
- Flat alternatives: trip_id, trip_start_time, trip_start_date, trip_route_id, trip_schedule_relationship, trip_is_active_on_create, trip_is_valid.

Trip payload processing rules:

- trip_id is required from either flat or nested source.
- start_time defaults to empty string when missing.
- start_date defaults to empty string when missing.
- route_id defaults to empty string when missing, then mapped.
- schedule_relationship defaults to SCHEDULED when missing.
- nested `trip.assignment_type` or flat `trip_assignment_type` is read into the normalized trip payload but not persisted unchanged.
- trip is_active_on_create defaults to True.
- trip is_valid defaults to True.
- mapped `route_id` replaces the original route ID in the normalized trip payload.

Derived matching inputs for vehicle_positions:

- scheduled_start_time: derived from trip_start_date + trip_start_time (or nested equivalents).
- scheduled_end_time: always None in current vehicle_positions flow.
- scheduled_start_stop_id: record.stop_id.
- scheduled_end_stop_id: record.stop_id.

Assignment behavior for vehicle_positions:

- If trip_id is nominal GTFS trip ID: trip_assignment_type and vehicle assignment_type become DIRECT_BY_ID.
- If trip_id is not nominal and match succeeds: both assignment fields become MATCHED_BY_CURRENT_STOP and trip_id is replaced by matched ID.
- If trip_id is not nominal and match fails: both assignment fields become NO_MATCH_GENERAL.

Invalid-reference policy effects for vehicle_positions:

- An invalid reference means at least one of these is true:
    - `trip.route_id` or flat route source is not contained in nominal GTFS route IDs after mapping.
    - optional `stop_id` is present but not contained in nominal GTFS stop IDs.
    - `trip_id` is neither a nominal GTFS trip ID nor successfully matched.
- Persisted `trip_is_valid` becomes false when the route or trip reference is invalid.
- Persisted vehicle `is_valid` becomes false when the route, stop, or trip reference is invalid.
- `discard_entire_object`: skip the full vehicle position and delete an existing synced vehicle with the same ID.
- `discard_invalid` and `discard_invalid_elements`:
    - clear trip `route_id` to an empty string when the mapped route is invalid.
    - deactivate the vehicle when `trip_id` is still unresolved or when no valid references remain.
- `keep_object_disabled`: keep the vehicle position but force vehicle `is_active` to false on create.

Fields not consumed from vehicle_positions:

- top-level assignment_type input is ignored.
- trip.assignment_type and flat trip_assignment_type inputs are ignored.
