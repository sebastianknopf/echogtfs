# EfaJsonServiceAlertsTransformer

## Input and Output

The transformer receives the decoded EFA JSON response and the configured source name. It selects records from `infos.current`, transforms supported entries into service-alert records, and returns a list of records. The datasource wraps the list in the standard envelope:

```python
{
    "record_type": "service_alerts",
    "records": [...],
}
```

An absent or empty `infos.current` list produces no records. A malformed response whose `infos.current` value is not a list is an invalid payload. Entries with an unsupported or missing `type` are skipped.

## Record Selection and Affected Entities

Create one alert record for each supported `info` entry. Read its type from `type` and its references from `affected`:

| `type` | References to include |
|---|---|
| `lineInfo` | Each `affected.lines[].id` as a route reference |
| `routeInfo` | Each affected route and each affected stop |
| `stopInfo` | Each `affected.stops[].id` as a stop reference |

For `routeInfo`, represent routes and stops as separate informed-entity entries in the same alert. Do not create a route-stop cross product. Ignore references outside the scope defined for each type. Skip an entry when it has no usable references.

Each route reference populates `route_id`; each stop reference populates `stop_id`. Set the other reference fields (`agency_id`, `route_type`, `trip_id`, and `direction_id`) to `None`. Initialize all four reference-validity flags to `True`; downstream processing performs nominal GTFS validation.

## Identifier

Use `properties.messageRef` as the upstream identifier, falling back to the entry's top-level `id`. Convert the identifier to a UUID using the shared deterministic datasource ID helper and the configured source name. Existing UUID identifiers remain unchanged. Skip an entry with neither identifier.

## Alert Fields

- Set `is_deleted` to `False` and `is_active` to `True`.
- EFA does not provide GTFS-Realtime cause or effect in the specified fields. Set `cause` to `UNKNOWN_CAUSE` and `effect` to `UNKNOWN_EFFECT`.
- Map `priority` to `severity_level`:
  - `normal` -> `INFO`
  - `high` -> `WARNING`
  - `veryHigh` -> `SEVERE`
  - Any other or missing value -> `UNKNOWN_SEVERITY`

## Translations and Text Normalization

Create one translation per `infoLinks[]` entry:

- `subtitle` supplies `header_text`.
- `content` supplies `description_text`.
- `url` supplies `url`.
- Use the source language when present; otherwise use `de-DE`.

Normalize `subtitle` and `content` as plain text. Decode HTML entities, convert line-break and block markup to line breaks, remove remaining markup, replace tabs with spaces, and collapse repeated whitespace while preserving meaningful line breaks. Keep the URL value as supplied.

If no usable information-link translations are available, emit one fallback translation with `language = de-DE`, `header_text = "Service Alert"`, and null description and URL.

## Validity Periods

Create one `active_periods` entry for each item in `timestamps.validity`:

- Use `period_type = "impact_period"`.
- Parse `from` and `to` as ISO-8601 timestamps and convert them to Unix seconds.
- Use `None` for a missing `from` or `to`.
- When `isOpenEnd` is `true`, set `end_time` to `None`.

`timestamps.availability` is the source publication timestamp. The normalized service-alert record has no publication-time field, so do not use it as an alert start time or include it in the output record.

## Returned Record Shape

Each record contains `id`, `is_deleted`, `cause`, `effect`, `severity_level`, `is_active`, `translations`, `active_periods`, and `informed_entities`, following the service-alert contract in [transformation.md](../transformation.md). Fields not specified by EFA use the defaults described above or the standard downstream processing defaults.
