# Differential and incremental Updates Implementation

## Runtime Flags and their Meaning

### Data Source Flag

- `is_differential_updates = false`: absence-based deletion is enabled for sync runs.
- `is_differential_updates = true`: absence-based deletion is disabled for sync runs.

### Trip Flag

- `is_complete_stop_sequence = true`: the record is treated as a full stop sequence and is eligible for full nominal propagation.
- `is_complete_stop_sequence = false`: the record is treated as partial/incremental and merged carefully with persisted state.

## Trip Update Synchronization Flow

`DatasourceBase._sync_trip_update_records` executes this order:

1. Read invalid-reference policy and `is_differential_updates` from the data source row.
2. Initialize identifier mapping and load nominal GTFS entity IDs.
3. Resolve existing realtime trips for this source and incoming trip UUIDs.
4. For each incoming trip-update record:
   - Map route and stop IDs.
   - Build stop-event validity from mapped stop IDs.
   - Resolve nominal trip matching if `trip_id` is not directly nominal.
   - Apply complete-sequence or incremental merge behavior.
   - Apply invalid-reference policy outcomes.
   - Upsert trip and replace stop events in one repository call.
5. After processing all records, optionally delete stale trips only when `is_differential_updates` is false.

## Complete Sequence Behavior

When `is_complete_stop_sequence` is true:

1. Nominal stop times are loaded by trip ID.
2. `_propagate_trip_update_stop_events` projects missing nominal stops and applies per-source behavior toggles:
   - `treat_unexpected_stop_as_added_stop`
   - `treat_missing_stop_as_canceled_stop`
3. Final stop events are renumbered in sequence order (`1..N`).
4. Scheduled anchors are persisted from the incoming record (`scheduled_start_*`, `scheduled_end_*`).
5. `start_time` is persisted from the incoming record.

## Incremental Sequence Behavior

When `is_complete_stop_sequence` is false, behavior depends on baseline availability:

1. If an existing persisted trip is complete (`existing_trip_model.is_complete_stop_sequence`):
   - persisted stop events are loaded,
   - `_merge_incremental_stop_events` merges incoming partial events into the existing full sequence,
   - `_propagate_incremental_delay` recomputes downstream arrival/departure estimates segment-by-segment,
   - merged result is renumbered (`1..N`),
   - persisted `is_complete_stop_sequence` remains `true`.
2. If no complete baseline exists:
   - incoming events are kept as partial,
   - `stop_sequence` is intentionally blank (`""`) for each stop event,
   - persisted `is_complete_stop_sequence` remains `false`.

For incremental updates, scheduled trip anchors and `start_time` are protected:

- complete baseline exists: keep existing `scheduled_start_*`, `scheduled_end_*`, and `start_time`.
- no complete baseline: keep anchors and `start_time` as `NULL` until a complete update arrives.

## Incremental Delay Propagation Details

`_propagate_incremental_delay` propagates timing from each explicitly matched stop to the next matched stop (or trip end):

1. Determine the reference delay from explicit departure, otherwise explicit arrival.
2. Propagate the delay to each intermediate stop arrival.
3. Compute departure from propagated delay.
4. At a timepoint (`scheduled_departure_time > scheduled_arrival_time`), early-running departures are clamped back to scheduled departure.
5. Late-running delays are never clamped and keep propagating.

This keeps incremental prognosis consistent with each stop's own `scheduled_*` values while allowing convergence at timepoints.

## Transformer Requirements For Incremental Support

`SiriEtTripUpdatesTransformer` provides the key signals used by sync logic:

1. `is_complete_stop_sequence` from `IsCompleteStopSequence`.
2. Scheduled anchors (`scheduled_start_*`, `scheduled_end_*`) only for complete sequences.
3. `start_time = None` for incomplete sequences.
4. `scheduled_intermediate_stops` extraction:
   - complete sequence: exclude first/last call (used as strong anchors),
   - incomplete sequence: include all delivered calls as fallback anchors.
5. Trip-window filter behavior:
   - complete sequence: reject trips where latest event is fully in the past,
   - incomplete sequence: allow records even if first delivered stop is in the recent past.

## Repository Persistence Semantics

`RealtimeRepository.update_trip_update_from_sync` persists trip updates as replace-on-write for stop events:

1. Create or update one `Trip` row (including `is_complete_stop_sequence` and nullable `start_time`).
2. Delete existing `StopEvent` rows for current `trip_id` (and previous `trip_id` if it changed).
3. Insert all provided stop events with normalized defaults (`original_stop_id`, `is_implied_schedule_relationship`).

The merge logic lives in `DatasourceBase`; the repository persists the already-resolved stop-event list atomically.

## Differential Deletion Semantics

Absence-based deletion of previously synced rows is disabled when a source is configured for differential updates.

Applied in `DatasourceBase`:

- Trip updates: `trips_to_delete` is empty when `is_differential_updates` is true.
- Vehicle positions: `vehicles_to_delete` is empty when `is_differential_updates` is true.

Policy-based explicit deletions (invalid-reference policy outcomes) still execute independently from differential mode.