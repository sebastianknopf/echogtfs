# EfaJsonServiceAlertsTransformer

This document specifies the EFA-JSON service-alert transformation. The registered EFA-JSON datasource is currently a placeholder, so the transformer behavior below is not implemented yet.

## Input and Entry Points

1. The datasource passes the decoded EFA JSON response and `source_name` to the transformer.
2. The datasource passes the configured `language` parameter to the transformer, following the existing pattern of passing transformer-specific parameters such as filters.
3. The transformer reads the information objects from `infos.current`.
4. Each supported information object is filtered and transformed into one service-alert record.
5. The transformer returns a list of records. The datasource wraps this list in the standard envelope:

   ```python
   {
       "record_type": "service_alerts",
       "records": [...],
   }
   ```

An absent or empty `infos.current` list produces no records. A present `infos.current` value that is not a list is an invalid payload.

## Top-Level Transform Flow

1. Read the information objects from `infos.current`.
2. For each object, check its type, identifier, affected references, and information links.
3. Discard objects with an unsupported type, no usable identifier, no applicable affected references, or no usable information link.
4. Apply the publication and validity window filter.
5. Convert retained objects to service-alert records and return them in source order.

## Information-Level Filtering Rules

The supported `type` values and their affected references are:

| `type` | References extracted |
|---|---|
| `lineInfo` | Each `affected.lines[].id` as a route reference. |
| `routeInfo` | Corresponding `affected.lines[].id` and `affected.stops[].id` values in one informed entity. |
| `stopInfo` | Each `affected.stops[].id` as a stop reference. |

Objects with a missing or unsupported `type` are skipped. A supported object without usable references for its type is also skipped.

For `routeInfo`, route and stop IDs are paired by their positions in the source arrays. A pair populates both `route_id` and `stop_id` on one informed entity; no route-stop cross product is created. An unmatched route or stop ID is retained in its own informed entity, with the other reference set to `None`.

The upstream identifier is read from `properties.messageRef`, falling back to the information object's top-level `id`. The identifier and `source_name` are passed to the shared datasource ID helper. Existing UUID values remain unchanged; other identifiers are converted to deterministic UUIDs. An object with neither identifier is skipped.

## Publication Window Rules

The EFA response can provide a publication window in `timestamps.availability` and impact windows in `timestamps.validity[]`. These windows are considered together when filtering an information object.

1. When neither source provides a window, the object passes the time-window filter.
2. When one or more windows are provided, the object passes if at least one parseable window is active or starts within the next 30 days.
3. A window is active when its start is at or before the current time and its end is absent or at or after the current time.
4. Objects for which all supplied windows have expired, or all start more than 30 days in the future, are discarded.
5. Timestamp parse failures are logged and the affected window is treated as non-matching.

This filter allows a valid publication window or a valid impact window to retain the alert. Expiration of one window type does not discard an alert whose other window type is still active or begins within the allowed future range.

## Active Period Extraction Rules

Active periods are built from both EFA time-window fields:

1. Each `timestamps.validity[]` item becomes an active period with `period_type = "impact_period"`.
2. `timestamps.availability` becomes an active period with `period_type = "communication_period"`.

For each period, `from` and `to` are parsed as ISO-8601 timestamps and converted to Unix seconds. Missing or invalid boundaries are represented as `None`; parse failures are logged. When `isOpenEnd` is `true`, `end_time` is `None`. Both publication and impact periods are included in the output for every retained alert.

## Translation Extraction Rules

### Language and Text Normalization

The transformer uses the configured datasource `language` for every output translation. Supported values are `de-DE`, `en-GB`, and `en-US`. Language metadata in the EFA response is ignored.

`subtitle` and `content` are normalized as plain text. HTML entities are decoded, line-break and block markup is converted to line breaks, remaining markup is removed, tabs are replaced with spaces, and repeated whitespace is collapsed while meaningful line breaks are preserved.

### Translation Assembly

Each usable `infoLinks[]` item produces one translation:

- `subtitle` supplies `header_text`.
- `content` supplies `description_text`.
- `url` supplies `url` when valid; otherwise the output value is `None`.
- The configured datasource language supplies `language`.

An information link is usable when its normalized subtitle or content is non-empty. A URL alone is not usable alert text. An alert without any usable information links is discarded; no fallback translation is produced.

### URL Validation

URLs are retained only when they are valid absolute HTTP or HTTPS URLs. Validation trims surrounding whitespace and requires an `http` or `https` scheme, a syntactically valid DNS name or IP address, and a valid authority. Explicit ports must be integers from 1 through 65535. Whitespace, control characters, malformed authorities, unsupported schemes, missing hosts, and invalid ports make the URL invalid.

A retained URL is stored in its trimmed form. DNS resolution and network reachability are not checked. Missing, non-string, or invalid URL values produce `url = None`.

## Informed Entity Extraction Rules

Each route reference populates `route_id`; each stop reference populates `stop_id`. The other reference fields (`agency_id`, `route_type`, `trip_id`, and `direction_id`) are `None`. All four per-reference validity flags are initialized to `True`; nominal GTFS validation is performed downstream.

## Returned Data Shape

Each output alert contains:

- `id` — stable UUID derived from the upstream identifier and source name.
- `is_deleted` — always `False`.
- `cause` — always `UNKNOWN_CAUSE`.
- `effect` — always `UNKNOWN_EFFECT`.
- `severity_level` — mapped from `priority`:
  - `normal` -> `INFO`
  - `high` -> `WARNING`
  - `veryHigh` -> `SEVERE`
  - any other or missing value -> `UNKNOWN_SEVERITY`
- `is_active` — always `True`.
- `translations`
- `active_periods`
- `informed_entities`

The record follows the service-alert contract in [transformation.md](../transformation.md). Fields not listed are handled using that contract's downstream defaults.
