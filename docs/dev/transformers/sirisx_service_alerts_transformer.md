# SiriSxServiceAlertsTransformer

## Input and Entry Points

1. The datasource passes XML root data to `transform()` as `{"root": xml_root, "source_name": ...}`.
2. `transform()` scans for all `PtSituationElement` nodes.
3. Each situation is filtered and then parsed via `_parse_situation_element_sirisx()`.

## Top-Level Transform Flow

1. Reset runtime metric and start timing.
2. Collect `PtSituationElement` nodes; return empty list when none exist.
3. For each situation:
	 - Apply participant filter.
	 - Apply publication-window filter.
	 - Parse situation into one internal alert dictionary.
4. Keep parse failures isolated per situation (error is logged, loop continues).
5. Log processing summary and store runtime in milliseconds.

## Situation-Level Filtering Rules

A situation is skipped when any of these conditions is met.

1. Participant filter is configured and `ParticipantRef` is missing or does not match any configured pattern.

Participant filter pattern behavior:

- Filter patterns are comma-separated.
- `*` matches any number of any characters.
- Matching uses full-value regex matching (`re.fullmatch`) after escaping literals and replacing `*` with `.*`.
2. Publication window check fails.
3. `SituationNumber` is missing.
4. No usable summary text can be extracted.

## Publication Window Rules

Publication windows are read from `PublicationWindow` elements.

1. If no publication windows are present, the situation is accepted.
2. If windows are present, a situation is accepted when at least one window matches:
	 - `start_time <= now <= end_time`, or
	 - `start_time > now` but within 30 days in the future.
3. Windows with start times more than 30 days ahead are ignored.
4. Parse errors in window timestamps are logged and treated as non-matching windows.

## Active Period Extraction Rules

Active periods are built from two sources:

1. `ValidityPeriod` -> `period_type = IMPACT_PERIOD`
2. `PublicationWindow` -> `period_type = COMMUNICATION_PERIOD`

For both:

- `StartTime` and `EndTime` are parsed to Unix timestamps.
- End dates with year `2500` are converted to `None`.
- Parse failures keep the field as `None` and emit warnings.

## Translation Extraction Rules

### Primary Text Sources

1. Top-level `Summary`, `Detail`, and `Description` on the situation.
2. If missing, fallback to a selected `PassengerInformationAction`:
	 - Prefer action with `Perspective = general`.
	 - Otherwise use first available passenger information action.
3. If still missing, fallback to selected `TextualContent`:
	 - Prefer `TextualContentSize = L`.
	 - Otherwise use first available textual content.

### TextualContent Mapping

From selected textual content:

- Header candidates: `SummaryContent/SummaryText`
- Description candidates: `DescriptionContent/DescriptionText`
- Fallback description sources when description is absent:
	- `ReasonContent/ReasonText`
	- `ConsequenceContent/ConsequenceText`

### Language and Text Normalization

- Language priority:
	1. `xml:lang` on text node
	2. situation `Language`
	3. system locale language
	4. fallback `de`
- All text is normalized through `_strip_html()`:
	- HTML tags removed.
	- Common entities decoded.
	- Break-like fragments and whitespace compacted.

### Translation Assembly

- One translation record per language key.
- `header_text` comes from summary values.
- `description_text` is concatenation of collected detail/description fragments with spaces.
- URL is taken from `InfoLink/Uri` (situation-level or selected action/textual content fallback).

## Informed Entity Extraction Rules

### Affects Source Priority

`Affects` blocks are resolved in this order:

1. `PublishingAction/PublishAtScope/Affects`
2. `Consequence/Affects`
3. Direct situation `Affects`

Each resolved `Affects` block is parsed independently.

### Entity Shapes

- Affected network/line:
	- `agency_id` from nested `OperatorRef` when present
	- `route_id` from `LineRef` when present
- Affected stop place / stop point:
	- `stop_id` from `StopPlaceRef` or `StopPointRef`
	- optional route/operator from nested affected lines
- Affected vehicle journey:
	- `trip_id` from `VehicleJourneyRef` or fallback `DatedVehicleJourneyRef`
	- optional `agency_id` from `Operator/OperatorRef`
	- optional stop references from `Route/StopPoints/AffectedStopPoint`
	- records produced with `is_trip_valid = False` for trip-linked entries

All informed-entity records include the following per-reference validity flags:

- `is_agency_valid`
- `is_route_valid`
- `is_stop_valid`
- `is_trip_valid`

Default values are `True` unless explicitly set otherwise by transformer-specific parsing rules.

No deduplication is applied in the transformer; extracted entities are appended as-is.

## Returned Data Shape

Each output alert dictionary contains:

- `id` (stable ID from `SituationNumber` and source)
- `cause = UNKNOWN_CAUSE`
- `effect = UNKNOWN_EFFECT`
- `severity_level = UNKNOWN_SEVERITY`
- `is_active = True`
- `translations`
- `active_periods`
- `informed_entities`

For normalized sync behavior and invalid-reference policy handling, see `docs/dev/transformation.md`.

## Runtime Metric

- `get_runtime_duration_ms()` returns full transform wall-clock runtime.
- Runtime is recorded even when all situations are filtered out.
