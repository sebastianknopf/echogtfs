# SiriVmVehiclePositionsTransformer

## Input and Entry Points

1. The datasource `SiriVmDatasource` passes XML root data to `transform()` as `{"root": xml_root, ...}`.
2. `transform()` scans the XML using namespace `http://www.siri.org.uk/siri` and collects all `VehicleActivity` nodes.
3. Each `VehicleActivity` is parsed independently by `_parse_vehicle_activity()`.

## Top-Level Transform Flow

1. Reset runtime metric (`_runtime_duration_ms = 0.0`) and start a timer with `perf_counter()`.
2. Read `VehicleActivity` elements:
   - If none are present, return an empty list.
3. Iterate all activities:
   - Call `_parse_vehicle_activity(activity)`.
   - If it returns `None`, count as filtered and continue.
   - If it returns a record, append to output.
   - If parsing raises an exception, log an error and continue with the next activity.
4. Return the list of parsed vehicle-position dictionaries.
5. Always store elapsed runtime in milliseconds in `_runtime_duration_ms` (via `finally`).

## Activity-Level Filtering Rules

A `VehicleActivity` is discarded (`None`) when any of these conditions is true.

1. `ValidUntilTime` is present and is in the past.
2. `RecordedAtTime` is present and older than 5 minutes.
3. `MonitoredVehicleJourney` is missing.
4. `Monitored` is present and not `true`.
5. Configured operator filter is set and `OperatorRef` is missing or does not match any configured pattern.
6. `VehicleStatus` equals `completed` (case-insensitive).
7. `FramedVehicleJourneyRef/DatedVehicleJourneyRef` (`trip_id`) is missing.
8. `LineRef` (`route_id`) is missing.
9. `VehicleRef` (`vehicle_id`) is missing.
10. `VehicleLocation/Longitude` or `VehicleLocation/Latitude` is missing.
11. Longitude/latitude cannot be parsed to float.
12. `IsCompleteStopSequence` is `true` and no usable call aimed times can be extracted from calls.

Operator filter pattern behavior:

- Filter patterns are comma-separated.
- `*` matches any number of any characters.
- Matching uses full-value regex matching (`re.fullmatch`) after escaping literals and replacing `*` with `.*`.

## Field Extraction Rules

### Core Trip and Vehicle Fields

- `trip.trip_id` from `FramedVehicleJourneyRef/DatedVehicleJourneyRef`.
- `trip.start_date` from `FramedVehicleJourneyRef/DataFrameRef` (default empty string).
- `trip.route_id` from `LineRef`.
- `vehicle_id` and `vehicle_label` from `VehicleRef`.
- `latitude` and `longitude` from `VehicleLocation` (float conversion required).

### Current Stop Status

- `MonitoredCall/StopPointRef` -> `stop_id`.
- `MonitoredCall/VehicleAtStop` controls status:
  - `true` -> `current_status = STOPPED_AT`
  - otherwise -> `current_status = IN_TRANSIT_TO`
- `MonitoredCall/Order` is parsed as integer for `current_stop_sequence`.
  - Non-integer values are ignored with a warning.

### Complete vs Incomplete Stop Sequence

`IsCompleteStopSequence` is parsed as boolean (default `false` when missing).

Call candidate collection order is fixed:

1. `PreviousCalls/PreviousCall` (in document order)
2. `MonitoredCall` (if present)
3. `OnwardCalls/OnwardCall` (in document order)

For each call candidate, the transformer builds `(stop_id, aimed_time)` tuples:

- `stop_id` from `StopPointRef`.
- `aimed_time` uses `AimedDepartureTime` first, otherwise `AimedArrivalTime`.
- Calls are included only when both `stop_id` and a parsed aimed time are present.

Rules per sequence mode:

1. `IsCompleteStopSequence = true`:
   - At least one usable tuple is required.
   - `scheduled_start_stop_id` and `scheduled_start_time` come from the first tuple.
   - `scheduled_end_stop_id` and `scheduled_end_time` come from the last tuple.
   - `scheduled_intermediate_stops` remains empty.

2. `IsCompleteStopSequence = false`:
   - `scheduled_start_stop_id` comes from `OriginRef`.
   - `scheduled_end_stop_id` comes from `DestinationRef`.
   - `scheduled_start_time` and `scheduled_end_time` stay `None`.
   - `scheduled_intermediate_stops` is a random sample of up to 3 tuples from extracted call tuples.
   - If no usable tuples exist, the activity is still kept (empty `scheduled_intermediate_stops`).

## Timestamp Resolution

1. Use `RecordedAtTime` when present and fresh.
2. Otherwise use `ValidUntilTime` when present.
3. Otherwise use current UTC time (`datetime.now(timezone.utc)`).

## Returned Data Shape

Each parsed record contains both nested and top-level scheduled fields.

- Nested trip object (`trip`) includes:
  - `trip_id`, `start_time`, `start_date`, `route_id`
  - `schedule_relationship = "SCHEDULED"`
  - `assignment_type = "ASSIGNED"`
  - `is_active = True`, `is_valid = True`
  - `scheduled_start_stop_id`, `scheduled_start_time`
  - `scheduled_end_stop_id`, `scheduled_end_time`
  - `scheduled_intermediate_stops`

- Top-level vehicle object includes:
  - `vehicle_id`, `vehicle_label`
  - `vehicle_wheelchair_accessible = UNKNOWN`
  - `timestamp`, `latitude`, `longitude`
  - `current_stop_sequence`, `current_status`, `stop_id`
  - `congestion_level = UNKNOWN_CONGESTION_LEVEL`
  - Duplicated schedule anchor fields (`scheduled_*`) for vehicle-level consumers.

For the normalized contract consumed by sync processing, see `docs/dev/transformation.md`.

## Helper Method Rules

- `_get_text(element)`: trims text, returns `None` for missing or empty values.
- `_parse_bool(value, default=...)`: only the string `"true"` (case-insensitive) maps to `True`; all other non-`None` values map to `False`.
- `_parse_datetime(value)`: parses ISO-8601, including `Z` suffix replacement to `+00:00`; invalid values return `None` and emit a warning.
- `_to_utc(value)`: treats naive datetimes as UTC; timezone-aware values are converted to UTC.

## Runtime Metric

- `get_runtime_duration_ms()` returns wall-clock transform runtime measured around the full `transform()` call.
- The runtime metric is available even when parsing returns early or encounters per-activity errors.