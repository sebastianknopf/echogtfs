# SiriSxSwissServiceAlertsTransformer

## Input and Entry Points

1. The datasource passes XML root data to `transform()` as `{"root": xml_root, "source_name": ...}`.
2. `transform()` scans for all `PtSituationElement` nodes.
3. Each situation is filtered and parsed by `_parse_situation()`.

## Top-Level Transform Flow

1. Reset runtime metric and start timing.
2. Collect all `PtSituationElement` nodes; return empty list if none exist.
3. For each situation:
	 - Apply participant filter.
	 - Apply publication-window filter.
	 - Parse to one internal service-alert dictionary.
4. Keep exceptions isolated per situation (error logged, processing continues).
5. Log transformed count and filter counters.
6. Persist runtime in milliseconds.

## Situation-Level Filtering Rules

A situation is skipped when any of these conditions is met.

1. Participant filter is configured and `ParticipantRef` is missing or does not match any configured pattern.

Participant filter pattern behavior:

- Filter patterns are comma-separated.
- `*` matches any number of any characters.
- Matching uses full-value regex matching (`re.fullmatch`) after escaping literals and replacing `*` with `.*`.
2. Publication window check fails.
3. `SituationNumber` is missing.
4. Translation extraction yields no meaningful text.

## Publication Window Rules

1. If no `PublicationWindow` elements exist, the situation is accepted.
2. If windows exist, at least one must match:
	 - current time between start and end, or
	 - start is in the future but within 30 days.
3. Windows with start times beyond 30 days are ignored.
4. Timestamp parse failures are logged and treated as non-matching windows.

## Active Period Extraction Rules

Active periods are generated from:

1. `ValidityPeriod` entries with `period_type = IMPACT_PERIOD`
2. `PublicationWindow` entries with `period_type = COMMUNICATION_PERIOD`

`StartTime` and `EndTime` are parsed to Unix timestamps. Parse errors keep `None` values.

## Translation Extraction Rules

### Source Selection

1. Find `PublishingAction/PassengerInformationAction` blocks.
2. Prefer the passenger information action that contains `Perspective = general`.
3. Otherwise use the first available passenger information action.
4. Inside that action, select `TextualContent`:
	 - Prefer `TextualContentSize = L`.
	 - Otherwise use first available textual content.

### Text Sections Used

From selected textual content:

- Header source: `SummaryContent/SummaryText`
- Description parts (appended in order):
	- `ReasonContent/ReasonText`
	- `DescriptionContent/DescriptionText`
	- `ConsequenceContent/ConsequenceText`
	- `RecommendationContent/RecommendationText`
	- `DurationContent/DurationText`
	- `RemarkContent/Remark`

Language is read from `xml:lang` and defaults to `de` when absent.

### URL Handling

- If `InfoLink/Uri` exists in selected textual content, it is assigned as `url` for all language variants.

### Translation Acceptance Rule

- Final translations are kept only if at least one language contains either non-empty `header_text` or `description_text`.
- If no meaningful text exists, the situation is discarded.

## Cause and Severity Mapping Rules

- `cause` comes from `AlertCause` via `_map_cause_swiss()`.
	- Unknown or missing values map to `UNKNOWN_CAUSE`.
- `severity_level` comes from `Severity` via `_map_severity_swiss()`.
	- Unknown or missing values map to `UNKNOWN_SEVERITY`.
- `effect` is always `UNKNOWN_EFFECT` in this transformer.

## Informed Entity Extraction Rules

### Affects Source Priority

`Affects` blocks are collected in this order:

1. `PublishingAction/PublishAtScope/Affects`
2. `Consequence/Affects`
3. Direct situation `Affects`

### Entity Extraction Patterns

- Affected network and line entries:
	- optional `agency_id` from `OperatorRef`
	- optional `route_id` from `LineRef`
- Affected stop place / stop point entries:
	- `stop_id` from `StopPlaceRef` or `StopPointRef`
	- optional route/operator from nested affected lines
- Affected vehicle journey entries:
	- `trip_id` from `VehicleJourneyRef` or fallback `DatedVehicleJourneyRef`
	- optional `agency_id` from `Operator/OperatorRef`
	- optional stop references from `Route/StopPoints/AffectedStopPoint`
	- emitted with `is_valid = False`

No deduplication is performed by the transformer.

## Returned Data Shape

Each output alert dictionary contains:

- `id`
- `cause`
- `effect`
- `severity_level`
- `is_active = True`
- `translations`
- `active_periods`
- `informed_entities`

For normalized sync behavior and invalid-reference handling, see `docs/dev/transformation.md`.

## Runtime Metric

- `get_runtime_duration_ms()` returns full transform wall-clock runtime.
- Runtime is recorded regardless of filtering outcome.
