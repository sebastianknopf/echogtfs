# Matching Service

## Purpose

The matching service resolves an external realtime `trip_id` to one unique nominal GTFS trip ID.

It is used when incoming realtime records reference a non-nominal trip ID and a deterministic mapping to one GTFS trip is required.

## Public Contract

The service method is asynchronous:

```python
match(
    *,
    trip_id: str,
    route_id: str | None = None,
    scheduled_start_time: datetime | None = None,
    scheduled_end_time: datetime | None = None,
    scheduled_start_stop_id: str | None = None,
    scheduled_end_stop_id: str | None = None,
    scheduled_intermediate_stops: list[tuple[str, datetime]] | None = None,
) -> str | None
```

Return value:

- One GTFS trip ID (`str`) when there is exactly one valid match.
- `None` when no unique match can be established.

## Matching Pipeline

Matching is executed in strict stages and stops as soon as one stage returns a unique result.

1. Cache stage.
2. Start/end anchor stage.
3. Intermediate stop fallback stage.

If no stage returns exactly one result, matching returns `None`.

## Stage 1: Cache Lookup

The cache is queried first with the external `trip_id`.

- If cache hit: return cached GTFS trip ID immediately.
- If cache miss: continue to stage 2.

No repository query is executed on cache hit.

## Global Preconditions

After cache miss, `route_id` is mandatory.

- If `route_id` is `None`, matching returns `None` directly.
- No repository query is executed in this case.

## ID Normalization Rules

Before repository calls:

- `scheduled_start_stop_id` is reduced via `GlobalId.level(..., 3)` when present.
- `scheduled_end_stop_id` is reduced via `GlobalId.level(..., 3)` when present.

For fallback anchors:

- Every intermediate stop ID is reduced via `GlobalId.level(..., 3)`.
- Entries with empty stop ID or non-datetime time value are discarded.

## Stage 2: Start/End Anchor Matching

This stage delegates to repository method `find_trip_ids_by_match_properties(...)`.

Input conditions:

- Executed only when `scheduled_start_time` is not `None`.

Repository parameters:

- `route_id`
- `scheduled_start_time`
- `scheduled_end_time`
- reduced `scheduled_start_stop_id`
- reduced `scheduled_end_stop_id`

Unique-match rule:

- If repository returns exactly one trip ID: success.
- If repository returns `None`, empty list, or more than one trip ID: stage fails.

Cache write:

- On success, cache is updated with `(external trip_id -> matched GTFS trip_id)`.

Time bias behavior:

- The stage itself delegates tolerance handling to repository queries.
- Repository-side start/end time matching uses a +/- 60 second window around provided anchor times.

## Stage 3: Intermediate Stop Fallback

This stage is only considered after stage 2 failure.

Execution guard:

- `scheduled_start_time is None`
- `scheduled_end_time is None`
- `scheduled_intermediate_stops` is present and not empty

If any of these conditions is false, matching returns `None` after stage 2.

### Candidate Selection

1. Query repository for route-scoped candidates:
   - `find_trip_ids_by_match_properties(route_id=route_id)`
2. If no candidates exist: return `None`.
3. For each candidate ID, load trip with stop times:
   - `get_gtfs_trip_with_stop_times(candidate_trip_id)`

### Per-Candidate Validation

A candidate trip matches only when all normalized intermediate anchors match at least one stop time in that trip.

For each anchor `(reduced_stop_id, scheduled_time)`:

1. Iterate all trip stop_times.
2. Keep only stop_times with:
   - string `stop_id`
   - non-null `departure_time`
3. Stop ID check:
   - candidate stop ID must start with reduced stop ID (prefix match).
4. Time check:
   - both times are converted to UTC.
   - absolute difference must be <= 60 seconds.

If any anchor has no matching stop_time, candidate is rejected.

### Fallback Success Rule

- If exactly one candidate trip remains: success.
- If zero or multiple candidates remain: fallback fails and returns `None`.

Cache write:

- On fallback success, cache is updated with `(external trip_id -> matched GTFS trip_id)`.

## Datetime Handling

Datetime normalization helper `_to_utc(value)` behaves as follows:

- Non-datetime input -> `None`.
- Naive datetime -> interpreted as UTC by attaching `timezone.utc`.
- Aware datetime -> converted to UTC with `astimezone(timezone.utc)`.

This normalization is used in intermediate-stop fallback comparisons.

## Determinism and Ambiguity Policy

The service enforces deterministic matching:

- Only one unique candidate is accepted.
- Ambiguous matches are rejected.
- Rejections are silent (`None`), not exceptions.

## Caching Semantics

Cache read key:

- external realtime `trip_id`.

Cache write occurs only when a unique match is found in stage 2 or stage 3.

No cache write occurs when:

- match fails,
- match is ambiguous,
- preconditions are not met.
