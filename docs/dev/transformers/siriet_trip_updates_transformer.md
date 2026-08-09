# SiriEtTripUpdatesTransformer

## Input and Entry Points

1. The datasource passes XML root data to `transform()` as `{"root": xml_root, ...}`.
2. `transform()` scans for `EstimatedVehicleJourney` elements.
3. Each journey is validated, parsed, and converted to one internal trip-update dictionary.

## Top-Level Transform Flow

1. Reset runtime metric and start runtime measurement.
2. Read all `EstimatedVehicleJourney` nodes.
3. For each journey, apply pre-parse filters in this order:
	- `Monitored` filter.
	- Operator filter (`OperatorRef` against configured allow-list).
	- NEW-trip completeness filter (`ExtraJourney=true` requires `IsCompleteStopSequence=true`).
4. Parse journey into an internal trip dictionary.
5. Apply trip time-window filter.
6. Append valid trip updates to output list.
7. Log summary counters and store runtime in milliseconds.

## Journey-Level Filtering Rules

A journey is skipped when any of these conditions is met.

1. `Monitored` is present and not `true`.
2. Configured operator filter is set and `OperatorRef` is missing or not allowed.
3. `ExtraJourney=true` and `IsCompleteStopSequence` is not `true`.
4. Parsing fails because required core fields/calls are missing.
5. Parsed trip is outside the active time window.

## Core Field Extraction Rules

- `trip_id` from `FramedVehicleJourneyRef/DatedVehicleJourneyRef`.
- `route_id` from `LineRef`.
- `start_date` from `FramedVehicleJourneyRef/DataFrameRef`.
- If either `trip_id` or `route_id` is missing, journey is discarded.

Call collection for schedule anchors uses:

1. All `RecordedCalls/RecordedCall` in XML order.
2. All `EstimatedCalls/EstimatedCall` in XML order.

From this combined list:

- First call defines scheduled start stop/time.
- Last call defines scheduled end stop/time.
- Start aimed time preference: `AimedDepartureTime`, then `AimedArrivalTime`.
- End aimed time preference: `AimedArrivalTime`, then `AimedDepartureTime`.

If start/end stop IDs cannot be resolved, the journey is discarded.

## Stop Event Extraction Rules

### RecordedCall

For each `RecordedCall` with `StopPointRef`:

1. Parse actual arrival/departure times first.
2. Fallback to aimed arrival/departure times when actual values are missing.
3. If one side is still missing, mirror the other side.
4. Set `schedule_relationship`:
	- `SKIPPED` when `Cancellation=true`
	- `NO_DATA` when no actual arrival/departure was provided
	- otherwise `SCHEDULED`

### EstimatedCall

For each `EstimatedCall` with `StopPointRef`:

1. Parse expected arrival/departure first.
2. Fallback to aimed arrival/departure when expected values are missing.
3. If one side is still missing, mirror the other side.
4. Set `schedule_relationship`:
	- `SKIPPED` when `Cancellation=true`
	- `ADDED` when `ExtraCall=true`
	- `NO_DATA` when no expected arrival/departure was provided
	- otherwise `SCHEDULED`

If no stop events are produced, the journey is discarded.

## Trip Relationship and Completeness Rules

- `schedule_relationship` defaults to `SCHEDULED`.
- If `ExtraJourney=true`, relationship is `NEW`.
- Else if `Cancellation=true`, relationship is `CANCELED`.
- Output `is_complete_stop_sequence` is currently always `True` for accepted journeys.

## Trip Window Rules

The parsed trip is accepted only if all checks pass:

1. At least one stop event exists.
2. First stop event has a usable timestamp (earlier of arrival/departure when both exist).
3. First timestamp is not more than 2 hours in the future.
4. At least one event timestamp exists at all.
5. Latest event timestamp is greater than or equal to current UTC time.

## Timezone and Start Time Formatting Rules

- Timezone source is `settings.timezone`.
- Invalid timezone configuration falls back to UTC.
- Naive datetimes are interpreted in the configured timezone and converted to UTC when needed.
- `start_time` formatting:
  - If `scheduled_start_time` is missing, result is empty string.
  - If `start_date` is known and local start is exactly next day, hours are encoded as `24+` (for example `25:10:00`).
  - Otherwise use `HH:MM:SS` local time.
- `start_date` fallback:
  - If missing and `scheduled_start_time` exists, it is set to the scheduled start date in ISO format.

## Returned Data Shape

Each output trip dictionary contains:

- `trip_id`
- `route_id`
- `start_time`
- `start_date`
- `schedule_relationship`
- `is_complete_stop_sequence`
- `scheduled_start_stop_id`
- `scheduled_end_stop_id`
- `scheduled_start_time`
- `scheduled_end_time`
- `stop_events`

For normalized sync and persistence semantics, see `docs/dev/transformation.md`.

## Helper Method Rules

- `_parse_bool(value, default=...)`: only `true` (case-insensitive) maps to `True`.
- `_parse_datetime(value)`: parses ISO datetimes and handles `Z`; invalid values return `None` and log warning.
- `_event_timestamp(stop_event)`: chooses earliest of arrival/departure when both exist.
- `_matches_operator_filter()`: allow-list is comma-separated and exact-match after trimming.

## Runtime Metric

- `get_runtime_duration_ms()` returns full transform wall-clock runtime.
- Runtime is recorded even if all journeys are filtered out.
