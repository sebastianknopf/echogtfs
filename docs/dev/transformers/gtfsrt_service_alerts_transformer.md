# GtfsRtServiceAlertsTransformer

## Input and Entry Points

1. The datasource passes parsed GTFS-RT feed data to `transform()` as `{"feed": feed_message, "source_name": ...}`.
2. `transform()` iterates `feed.entity` and processes only entities containing an `alert` field.
3. Each valid alert entity is converted into one internal service-alert dictionary.

## Top-Level Transform Flow

1. Reset runtime metric and start runtime measurement with `perf_counter()`.
2. Iterate all entities in the feed.
3. Skip entities that do not contain `alert`.
4. For each alert entity:
	- Build a stable internal alert ID via `make_unique_id(entity.id, source_name)`.
	- Map cause, effect, and severity (with unknown fallbacks).
	- Build translations.
	- Build active periods.
	- Apply time-window filtering.
	- Build informed entities.
	- Append the normalized alert record.
5. Log filtered counts and transformed alert count.
6. Always store runtime duration in milliseconds in `_runtime_duration_ms`.

## Enumeration Mapping Rules

- `cause`:
  - Numeric GTFS-RT values are mapped via `_map_cause()`.
  - Missing or unknown values map to `UNKNOWN_CAUSE`.
- `effect`:
  - Numeric GTFS-RT values are mapped via `_map_effect()`.
  - Missing or unknown values map to `UNKNOWN_EFFECT`.
- `severity_level`:
  - Numeric GTFS-RT values are mapped via `_map_severity()`.
  - Missing or unknown values map to `UNKNOWN_SEVERITY`.

## Translation Extraction Rules

1. Translations are built from `alert.header_text.translation` entries.
2. For each header translation:
	- `language` defaults to `de-DE` when missing.
	- `header_text` is taken from translation text when present.
3. `description_text` lookup:
	- Search in `alert.description_text.translation` for the same language.
	- A description entry without language is treated as `de-DE`.
4. `url` lookup:
	- Search in `alert.url.translation` for the same language.
	- A URL entry without language is treated as `de-DE`.
5. If no translations can be built from headers, the transformer creates one fallback translation:
	- `language = de-DE`
	- `header_text = Service Alert`
	- `description_text = None`
	- `url = None`

## Active Period Construction and Filtering

### Period Construction

1. Add one period per `impact_period` element with `period_type = IMPACT_PERIOD`.
2. Add one period per `communication_period` element with `period_type = COMMUNICATION_PERIOD`.
3. If neither of the above exists, fallback to `active_period` entries with `period_type = IMPACT_PERIOD`.
4. `start_time` and `end_time` remain `None` when fields are absent.

### Time-Window Filtering

Filtering is applied only when at least one period exists.

1. Not-yet-valid filter:
	- Find the earliest non-null period start.
	- If it is more than 30 days in the future, discard the alert.
2. Expired filter:
	- Find the maximum non-null period end.
	- If it is before current timestamp, discard the alert.

## Informed Entity Extraction Rules

For each `alert.informed_entity` selector, create one dictionary with:

- `agency_id` from `agency_id` if present.
- `route_id` from `route_id` if present.
- `route_type` from `route_type` if present.
- `stop_id` from `stop_id` if present.
- `trip_id` from `trip.trip_id` if present.
- `direction_id` from `trip.direction_id` if present.
- `is_agency_valid = True`
- `is_route_valid = True`
- `is_stop_valid = True`
- `is_trip_valid = True`

Missing values are stored as `None`.

## Returned Data Shape

Each output record contains:

- `id`
- `cause`
- `effect`
- `severity_level`
- `is_active` (always `True` at transform stage)
- `translations`
- `active_periods`
- `informed_entities`

For the normalized sync contract and persistence behavior, see `docs/dev/transformation.md`.

## Runtime Metric

- `get_runtime_duration_ms()` returns full transform wall-clock runtime.
- Runtime is recorded even when alerts are filtered or an exception path is taken.
