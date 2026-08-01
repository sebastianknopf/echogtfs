# Transformer Return Model

## Relevant Files

- `backend/src/echogtfs/datasources/base.py`
- `backend/src/echogtfs/services/database/realtime_repository.py`
- `backend/src/echogtfs/services/mapping/identifier_mapping_service.py`

## Transformer Contract

Transformer output is consumed by DatasourceBase._fetch_records and normalized by DatasourceBase._normalize_fetched_payload.

A transformer can return one of the following shapes:

1. Envelope format:

```python
{
    "record_type": "service_alerts" | "trip_updates" | "vehicle_positions",
    "records": [
        # list[dict[str, Any]]
    ],
}
```

2. Legacy format:

```python
[
    # list[dict[str, Any]]
]
```

The legacy format is treated as record_type="service_alerts".

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

Mapped fields in service_alerts:

- informed_entities[*].agency_id
- informed_entities[*].route_id
- informed_entities[*].stop_id

Not mapped in service_alerts:

- informed_entities[*].trip_id

## record_type trip_updates

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

Derived matching inputs for trip_updates:

- scheduled_start_time: derived from start_date + start_time via %Y%m%d %H:%M:%S parser.
- scheduled_end_time: derived from last stop event departure_time, or arrival_time fallback, parsed as datetime/ISO string; otherwise None.
- scheduled_start_stop_id: first stop_events[*].stop_id after mapping, or None.
- scheduled_end_stop_id: last stop_events[*].stop_id after mapping, or None.

Assignment behavior for trip_updates:

- If trip_id is nominal GTFS trip ID: assignment_type becomes DIRECT_BY_ID.
- If trip_id is not nominal and match succeeds: assignment_type becomes MATCHED_BY_START_STOP and trip_id is replaced by matched ID.
- If trip_id is not nominal and match fails: assignment_type becomes NO_MATCH_GENERAL.

Fields not consumed from trip_updates:

- top-level assignment_type input is ignored and overwritten by derived assignment_type.

## record_type vehicle_positions

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
- trip is_active_on_create defaults to True.
- trip is_valid defaults to True.

Derived matching inputs for vehicle_positions:

- scheduled_start_time: derived from trip_start_date + trip_start_time (or nested equivalents).
- scheduled_end_time: always None in current vehicle_positions flow.
- scheduled_start_stop_id: record.stop_id.
- scheduled_end_stop_id: record.stop_id.

Assignment behavior for vehicle_positions:

- If trip_id is nominal GTFS trip ID: trip_assignment_type and vehicle assignment_type become DIRECT_BY_ID.
- If trip_id is not nominal and match succeeds: both assignment fields become MATCHED_BY_CURRENT_STOP and trip_id is replaced by matched ID.
- If trip_id is not nominal and match fails: both assignment fields become NO_MATCH_GENERAL.

Fields not consumed from vehicle_positions:

- top-level assignment_type input is ignored.
- trip.assignment_type and flat trip_assignment_type inputs are ignored.

Pipeline order used by DatasourceBase:

1. Load records from transformer.
2. Normalize payload shape into (record_type, records).
3. Initialize mapping/enrichment/matching dependencies for the current source.
4. Apply identifier mapping to route_id and stop_id fields where relevant.
5. For trip-related records, conditionally run matching when trip_id is not in nominal GTFS trip IDs.
6. Upsert records into realtime tables.

## record_type service_alerts

Each record must provide the fields required by _sync_service_alert_records and RealtimeRepository.upsert_service_alert_from_sync.

Full allowed model:

```python
{
    "id": str,  # required
    "cause": str,  # required
    "effect": str,  # required
    "severity_level": str,  # required
    "is_active": bool,  # optional, default True
    "translations": [  # optional, default []
        {
            "language": str,  # required
            "header_text": str | None,  # optional
            "description_text": str | None,  # optional
            "url": str | None,  # optional
        }
    ],
    "active_periods": [  # optional, default []
        {
            "period_type": str,  # optional, defaults in persistence layer
            "start_time": int | None,  # optional
            "end_time": int | None,  # optional
        }
    ],
    "informed_entities": [  # optional, default []
        {
            "agency_id": str | None,
            "route_id": str | None,
            "route_type": int | None,
            "stop_id": str | None,
            "trip_id": str | None,
            "direction_id": int | None,
            "is_valid": bool,  # optional; may be assigned by validation flow
        }
    ],
}
```

```python
{
    "id": "external-alert-id-or-uuid",
    "cause": "UNKNOWN_CAUSE",
    "effect": "UNKNOWN_EFFECT",
    "severity_level": "UNKNOWN_SEVERITY",
    "is_active": True,
    "translations": [
        {
            "language": "en",
            "header_text": "Line disruption",
            "description_text": "Replacement buses between A and B",
            "url": "https://example.invalid/notice",
        }
    ],
    "active_periods": [
        {
            "period_type": "impact_period",
            "start_time": 1754044800,
            "end_time": 1754052000,
        }
    ],
    "informed_entities": [
        {
            "agency_id": None,
            "route_id": "R10",
            "route_type": None,
            "stop_id": "8503000",
            "trip_id": None,
            "direction_id": None,
        }
    ],
}
```

Notes:

- agency_id, stop_id and route_id are subject to identifier mapping.

**Important Note:** Trip based informed entities are currently not supported and are ignored!

## record_type trip_updates

Each record must provide the fields required by _sync_trip_update_records and RealtimeRepository.update_trip_update_from_sync.

Full allowed model:

```python
{
    "id": str,  # optional; if missing, trip_id is used for deterministic UUID
    "trip_id": str,  # required
    "start_time": str,  # required, HH:MM:SS
    "start_date": str,  # required, YYYYMMDD
    "route_id": str,  # required
    "schedule_relationship": str,  # optional, default "SCHEDULED"
    "assignment_type": str,  # optional input; overwritten by DatasourceBase
    "is_active": bool,  # optional, default True
    "is_valid": bool,  # optional, default True
    "stop_events": [  # optional, default []
        {
            "trip_id": str,  # optional input; ignored and replaced by persisted trip_id
            "stop_id": str,  # required for persistence
            "stop_sequence": str,  # required for persistence
            "arrival_time": str | datetime,  # required for persistence
            "departure_time": str | datetime,  # required for persistence
            "schedule_relationship": str,  # optional, default "SCHEDULED"
            "is_valid": bool,  # optional, default True
        }
    ],
}
```

```python
{
    "id": "external-trip-update-id",
    "trip_id": "trip-20260801-001",
    "start_time": "08:05:00",
    "start_date": "20260801",
    "route_id": "R10",
    "schedule_relationship": "SCHEDULED",
    "is_active": True,
    "is_valid": True,
    "stop_events": [
        {
            "stop_id": "8503000",
            "stop_sequence": "1",
            "arrival_time": "2026-08-01T08:05:00Z",
            "departure_time": "2026-08-01T08:06:00Z",
            "schedule_relationship": "SCHEDULED",
            "is_valid": True,
        },
        {
            "stop_id": "8503010",
            "stop_sequence": "2",
            "arrival_time": "2026-08-01T08:12:00Z",
            "departure_time": "2026-08-01T08:13:00Z",
            "schedule_relationship": "SCHEDULED",
            "is_valid": True,
        },
    ],
}
```

Notes:

- route_id and stop_events[*].stop_id are subject to identifier mapping.
- assignment_type is derived inside DatasourceBase from direct ID match or matching-service result.

## record_type vehicle_positions

Each record must provide the fields required by _sync_vehicle_position_records and RealtimeRepository.update_vehicle_position_from_sync.

Full allowed model:

```python
{
    "id": str,  # optional; if missing, vehicle_id is used for deterministic UUID

    # Trip descriptor can be provided nested or as flat fields.
    "trip": {
        "trip_id": str,  # required if root trip_id not set
        "start_time": str,  # optional fallback to ""
        "start_date": str,  # optional fallback to ""
        "route_id": str,  # optional fallback to ""
        "schedule_relationship": str,  # optional, default "SCHEDULED"
        "assignment_type": str,  # optional input; overwritten by DatasourceBase
        "is_active": bool,  # optional fallback for trip_is_active_on_create
        "is_valid": bool,  # optional fallback for trip_is_valid
    },

    # Flat trip alternatives
    "trip_id": str,
    "trip_start_time": str,
    "trip_start_date": str,
    "trip_route_id": str,
    "trip_schedule_relationship": str,
    "trip_assignment_type": str,  # optional input; overwritten by DatasourceBase
    "trip_is_active_on_create": bool,
    "trip_is_valid": bool,

    # Vehicle fields
    "vehicle_id": str,  # required
    "vehicle_label": str | None,  # optional
    "vehicle_license_plate": str | None,  # optional
    "vehicle_wheelchair_accessible": str,  # optional, default "NO_VALUE"
    "timestamp": str | datetime,  # required
    "latitude": float | int,  # required
    "longitude": float | int,  # required
    "current_stop_sequence": int,  # optional, default 0
    "current_status": str,  # optional, default "IN_TRANSIT_TO"
    "assignment_type": str,  # optional input; overwritten by DatasourceBase
    "congestion_level": str,  # optional, default "UNKNOWN_CONGESTION_LEVEL"
    "is_active": bool,  # optional, default True
    "is_valid": bool,  # optional, default True

    # Optional stop hint used only by matching flow
    "stop_id": str,
}
```

```python
{
    "id": "external-vehicle-position-id",
    "trip": {
        "trip_id": "trip-20260801-001",
        "start_time": "08:05:00",
        "start_date": "20260801",
        "route_id": "R10",
        "schedule_relationship": "SCHEDULED",
    },
    "vehicle_id": "vehicle-4711",
    "vehicle_label": "Bus 4711",
    "vehicle_license_plate": "ZH123456",
    "vehicle_wheelchair_accessible": "NO_VALUE",
    "timestamp": "2026-08-01T08:07:30Z",
    "latitude": 47.3763,
    "longitude": 8.5476,
    "current_stop_sequence": 1,
    "current_status": "IN_TRANSIT_TO",
    "congestion_level": "UNKNOWN_CONGESTION_LEVEL",
    "is_active": True,
    "is_valid": True,
}
```

Alternative flat trip fields are also accepted by DatasourceBase:

- trip_id
- trip_start_time
- trip_start_date
- trip_route_id
- trip_schedule_relationship

Notes:

- route_id is subject to identifier mapping.
- assignment_type and trip_assignment_type are derived inside DatasourceBase from direct ID match or matching-service result.
