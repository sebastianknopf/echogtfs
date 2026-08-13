# Matching Service

## Purpose

The matching service resolves an external realtime `trip_id` to one unique nominal GTFS trip ID. It returns `None` when it cannot establish a unique match.

## Public Contract

The service method is asynchronous:

```python
match(
    *,
    trip_id: str,
    route_id: str | None = None,
    operation_day_date: date | None = None,
    scheduled_start_time: datetime | None = None,
    scheduled_end_time: datetime | None = None,
    scheduled_start_stop_id: str | None = None,
    scheduled_end_stop_id: str | None = None,
    scheduled_intermediate_stops: list[tuple[str, datetime]] | None = None,
) -> str | None
```

The result is one GTFS trip ID when exactly one valid match is found. Cache hits are returned immediately. No exception is raised for missing, invalid, or ambiguous matches.

## Matching Pipeline

After the cache lookup and route precondition, matching proceeds in this order:

1. Start/end anchor matching.
2. Intermediate-stop fallback, only when both scheduled anchor times are absent.

The service caches a result only after either matching stage returns exactly one trip ID.

## Cache Lookup and Preconditions

The cache is queried first with the external `trip_id`. A cache hit returns the cached GTFS trip ID without a repository query.

After a cache miss, `route_id` is required. If it is `None`, matching returns `None` without querying the repository.

## ID Normalization

Before start/end matching, present `scheduled_start_stop_id` and `scheduled_end_stop_id` values are reduced with `GlobalId.level(..., 3)`.

Before intermediate-stop matching, each anchor is validated and normalized:

- Empty stop IDs are discarded.
- Entries whose time is not a `datetime` are discarded.
- Remaining stop IDs are reduced with `GlobalId.level(..., 3)`.

If all supplied intermediate anchors are discarded, fallback matching is not attempted.

## Start/End Anchor Matching

This stage runs only when `scheduled_start_time` is not `None`. It calls `find_trip_ids_by_match_properties(...)` with:

- `route_id`
- `operation_day_date`
- `scheduled_start_time`
- `scheduled_end_time`
- normalized start and end stop IDs

When `operation_day_date` is `None`, the service uses `scheduled_start_time.date()` for this repository call. The repository determines which trips satisfy the supplied match properties, including any time matching rules.

The stage succeeds only when the repository returns exactly one trip ID. On success, the service caches the mapping from the external `trip_id` to that GTFS trip ID. Otherwise, it proceeds to the fallback checks.

## Intermediate-Stop Fallback

Fallback matching runs only when all of the following are true:

- `scheduled_start_time is None`
- `scheduled_end_time is None`
- `scheduled_intermediate_stops` is non-empty
- At least one intermediate anchor remains after normalization

The service first requests route-scoped candidate IDs with `find_trip_ids_by_match_properties(...)`, passing `route_id` and the supplied `operation_day_date`. If no candidates are returned, fallback fails.

For each candidate, the service loads the trip and its stop times with `get_gtfs_trip_with_stop_times(...)`. A candidate matches only when every normalized intermediate anchor matches at least one stop time:

1. The trip must have a non-empty `stop_times` list.
2. The stop time must have a string `stop_id` and a non-null `departure_time`.
3. The candidate stop ID must start with the normalized anchor stop ID.
4. Both departure and scheduled times must be datetimes whose UTC values differ by no more than 60 seconds.

If any anchor has no matching stop time, the candidate is rejected. Fallback succeeds only when exactly one candidate remains. That result is then cached.

## Datetime Handling

The fallback comparison converts datetimes with `_to_utc(value)`:

- Non-datetime values produce `None`.
- Naive datetimes are interpreted as UTC.
- Aware datetimes are converted to UTC.

An anchor cannot match when either time cannot be converted to UTC.

## Determinism and Caching

Only one unique candidate is accepted. Zero candidates and ambiguous results return `None` silently.

The cache key is the external realtime `trip_id`. No cache write occurs when matching fails, is ambiguous, or stops at a precondition or normalization check.
