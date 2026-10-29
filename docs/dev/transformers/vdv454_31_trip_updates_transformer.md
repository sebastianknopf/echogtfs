# VDV454 3.1 Trip Updates Transformer

## Concept Mapping

| VDV454 AUS | SIRI-ET equivalent | Internal field |
| --- | --- | --- |
| `IstFahrt` | `EstimatedVehicleJourney` | one trip-update record |
| `IstHalt` | `RecordedCall` / `EstimatedCall` | one stop event |
| `Komplettfahrt` | `IsCompleteStopSequence` | `is_complete_stop_sequence` |
| `Zusatzfahrt` | `ExtraJourney` | `schedule_relationship = NEW` |
| `FaelltAus` | `Cancellation` | `schedule_relationship = CANCELED` |
| `Zusatzhalt` | `ExtraCall` | stop event `ADDED` |
| `FahrtRef/FahrtStartEnde` | none | scheduled start/end anchors |

VDV454 differs from SIRI-ET in these points, which shape the rules below:

- A single `IstHalt` carries arrival and departure, so one stop event is produced per `IstHalt`. There is no separate recorded/estimated distinction; the real-time state is given by `IstAnkunftPrognoseStatus` / `IstAbfahrtPrognoseStatus`.
- `IstHalt` has no sequence number. The order in the document is the travel order.
- Messages are differential. `Komplettfahrt=true` sets a new base state of the trip. `Komplettfahrt=false` only changes the transmitted stops and attributes (VDV454 chapters 4.7.1, 4.7.3, 6.1.2).
- The original scheduled start and end of the trip are transmitted in `FahrtRef/FahrtStartEnde` and never change, even after reroutes or shortenings (chapter 5.2.2.2.1).
- Times are UTC unless an offset is given (chapter 3.6).

## Input and Entry Points

1. The datasource passes XML root data to `transform()` as `{"root": xml_root, ...}`. The root is a `DatenAbrufenAntwort` element.
2. `transform()` scans for `IstFahrt` elements inside `AUSNachricht` elements. Element names are not namespace-qualified.
3. Each journey is validated, parsed, and converted to one internal trip-update dictionary.
4. `Bestaetigung`, `WeitereDaten`, `AboID`, and `IstFahrt/@Zst` are not evaluated by the transformer.

## Data Source Requirement

VDV454 AUS is a differential feed. Absence of a journey in a delivery does not mean the journey ended. The data source must run with `is_differential_updates = true` (see [differential-incremental.md](../differential-incremental.md)). Removal is signalled with `is_deleted` records only.

## Top-Level Transform Flow

1. Reset runtime metric and start runtime measurement.
2. Read all `IstFahrt` nodes.
3. For each journey, apply pre-parse filters in this order:
	- Operator filter (`BetreiberID` against configured wildcard patterns).
	- Line filter (`LinienID` against configured wildcard patterns).
	- Reset check (`FahrtZuruecksetzen=true` produces a deletion record and ends processing of the journey).
	- NEW-trip completeness filter (`Zusatzfahrt=true` requires `Komplettfahrt=true`).
4. Parse journey into an internal trip dictionary.
5. Apply trip time-window filter.
6. Append valid trip updates and deletion records to output list in delivery order.
7. Log processed and total filtered counts, then store runtime in milliseconds.

## Filtering

The datasource parses the configured filter, using commas or whitespace as separators, into the transformer's `line`, `operator`, and `legacy` pattern lists. Unprefixed values and `operator/` values filter `BetreiberID`. `line/` values filter `LinienID`.

`*` matches any number of characters, and matching covers the complete value. A configured operator or line filter rejects a journey when the corresponding element is missing or does not match any configured pattern. `RichtungsID` is not filtered.

## Journey-Level Filtering Rules

A journey is skipped when any of these conditions is met.

1. Configured operator filter is set and `BetreiberID` is missing or does not match any configured pattern.
2. Configured line filter is set and `LinienID` is missing or does not match any configured pattern.
3. `Zusatzfahrt=true` and `Komplettfahrt` is not `true`.
4. Parsing fails because required core fields are missing.
5. Parsed trip is outside the active time window.

There is no equivalent of the SIRI `Monitored` filter. `PrognoseMoeglich=false` does not skip a journey, see [Real-Time Availability](#real-time-availability).

## Core Field Extraction Rules

- `trip_id` from `FahrtRef/FahrtID/FahrtBezeichner`.
- `route_id` from `LinienID`.
- `start_date` from `FahrtRef/FahrtID/Betriebstag`, as delivered (`YYYY-MM-DD`).
- If `trip_id` or `route_id` is missing, the journey is discarded. A journey that references the trip only through `FahrtStartEnde` (no `FahrtID`) is discarded.

Scheduled anchors:

- If `FahrtRef/FahrtStartEnde` exists:
	- `scheduled_start_stop_id` from `StartHaltID`, `scheduled_start_time` from `Startzeit`.
	- `scheduled_end_stop_id` from `EndHaltID`, `scheduled_end_time` from `Endzeit`.
	- The anchors are set for complete and incomplete journeys, because `FahrtStartEnde` always refers to the original scheduled trip.
- If `FahrtStartEnde` is missing, the anchors are derived from the first and the last `IstHalt` in document order:
	- Start stop ID from the first `IstHalt`, end stop ID from the last `IstHalt`.
	- Start time: `Abfahrtszeit`, then `Ankunftszeit` of the first `IstHalt`.
	- End time: `Ankunftszeit`, then `Abfahrtszeit` of the last `IstHalt`.
	- Times are only set when `Komplettfahrt=true`; for incomplete journeys they are `None`, because the first and last delivered stop are not trip anchors.

If the start or end stop ID cannot be resolved, the journey is discarded. A resolvable stop ID is the value of `HaltID/HaltestellenID`.

`scheduled_intermediate_stops` is built from `IstHalt` elements in document order, using `Abfahrtszeit`, then `Ankunftszeit` as scheduled time:

- Complete journey: all `IstHalt` except the first and the last one.
- Incomplete journey: all delivered `IstHalt`.
- Stops without stop ID or without scheduled time are skipped.

## Stop Event Extraction Rules

For each `IstHalt` with a resolvable `HaltID/HaltestellenID`:

1. `stop_id` is `HaltID/HaltestellenID`.
2. `stop_sequence`:
	- Complete journey: 1-based position of the `IstHalt` in document order, as string.
	- Incomplete journey: empty string, because the position within a partial delivery says nothing about the position in the trip.
3. `scheduled_arrival_time` is `Ankunftszeit`, `scheduled_departure_time` is `Abfahrtszeit`. Missing values stay `None`.
4. Expected times:
	- `arrival_time` from `IstAnkunftPrognose`, unless `IstAnkunftPrognoseStatus` is `Unbekannt`.
	- `departure_time` from `IstAbfahrtPrognose`, unless `IstAbfahrtPrognoseStatus` is `Unbekannt`.
	- The status values `Prognose` (default when the status is absent), `Real`, and `Geschaetzt` all yield an expected time. The status itself is not part of the output.
5. Fallback to scheduled times (`Ankunftszeit`, `Abfahrtszeit`) when expected values are missing.
6. If one side is still missing, mirror the other side. The first stop typically has no arrival, the last stop typically has no departure.
7. Set `schedule_relationship`, first match wins:
	- `SKIPPED` when `Durchfahrt=true`.
	- `ADDED` when `Zusatzhalt=true`.
	- `NO_DATA` when no expected arrival and no expected departure was used (see also [Real-Time Availability](#real-time-availability)).
	- otherwise `SCHEDULED`.

`IstHalt` elements are neither reordered nor deduplicated. Stops delivered by a `Komplettfahrt` replace the previous state of the trip; stops missing from it are not extractable and are handled by the consumer (`treat_missing_stop_as_canceled_stop`, see [stop-propagation.md](../stop-propagation.md)).

If no stop events are produced, the journey is discarded, except for the cases listed in [Journeys Without IstHalt](#journeys-without-isthalt).

### Real-Time Availability

- `PrognoseMoeglich=false` means that no real-time prediction exists for the not yet served stops. All prediction fields are ignored, expected times fall back to scheduled times, and all stop events get `NO_DATA` (except `SKIPPED` and `ADDED`).
- `PrognoseMoeglich` missing counts as `true` (processing rule of the specification).

### Journeys Without IstHalt

`IstHalt` is optional in the schema. A journey without `IstHalt` is kept when `FaelltAus=true`. It is returned with empty `stop_events`, `schedule_relationship = CANCELED`, and the anchors from `FahrtStartEnde`. Without `FahrtStartEnde` it is discarded. All other journeys without `IstHalt` (attribute-only messages) are discarded.

## Trip Relationship and Completeness Rules

- `schedule_relationship` defaults to `SCHEDULED`.
- If `Zusatzfahrt=true`, relationship is `NEW`.
- Else if `FaelltAus=true`, relationship is `CANCELED`.
- `is_complete_stop_sequence` is `true` only when `Komplettfahrt` is `true`.
- `FahrtZuruecksetzen=true` produces a deletion record instead of a trip update: `{"trip_id": ..., "is_deleted": True}`. The record is not parsed further and bypasses the trip time-window filter. Semantics of deletion records are defined in [transformation.md](../transformation.md).

## Trip Window Rules

The parsed trip is accepted only if all checks pass:

1. At least one stop event exists. Cancelled journeys without stop events use `Startzeit` as first timestamp and `Endzeit` as latest timestamp.
2. First stop event has a usable timestamp (earlier of arrival/departure when both exist).
3. First timestamp is not more than 2 hours in the future.
4. Complete journeys only: at least one event timestamp exists and the latest event timestamp is greater than or equal to current UTC time.
5. Incomplete journeys skip check 4, because a partial delivery may legitimately contain only stops in the recent past.

## Timezone and Start Time Formatting Rules

- Timestamps without UTC offset are interpreted as UTC (VDV454 chapter 3.6). This differs from the SIRI-ET transformer, which uses the configured timezone for naive values. Values with `Z` or an offset are converted to UTC.
- `settings.timezone` is only used to format `start_time`. Invalid timezone configuration falls back to UTC.
- `start_time` is derived from `scheduled_start_time` (or the first-stop fallback of the anchor rules) and set only for complete journeys, otherwise `None`:
  - If no scheduled start time exists, result is empty string.
  - If the local start date is exactly the day after `start_date`, hours are encoded as `24+` (for example `25:10:00`). `Betriebstag` may differ from the calendar day (VDV454 chapter 5.1.3.1).
  - Otherwise use `HH:MM:SS` local time.
- `start_date` stays as delivered. If missing and a scheduled start time exists, it is set to the local scheduled start date in ISO format.

## Returned Data Shape

Each output trip dictionary contains:

- `trip_id`
- `is_deleted` (`False`)
- `route_id`
- `start_time`
- `start_date`
- `schedule_relationship`
- `is_complete_stop_sequence`
- `scheduled_start_stop_id`
- `scheduled_end_stop_id`
- `scheduled_start_time`
- `scheduled_end_time`
- `scheduled_intermediate_stops`
- `stop_events`, each with `stop_id`, `stop_sequence`, `arrival_time`, `departure_time`, `scheduled_arrival_time`, `scheduled_departure_time`, `schedule_relationship`

Fields not listed are set by the consumer (`id`, `original_trip_id`, `assignment_type`, validity flags, `is_active`). For normalized sync and persistence semantics, see [transformation.md](../transformation.md).

## Elements Not Extracted

These elements have no counterpart in the internal model and are ignored: `Protokolleintrag`, `BetrieblicheFahrtnummern`, `UmlaufID`, `KursNr`, `AusfuehrenderID`, `OriginalSollFahrtverlauf`, `DispoID`, `FahrtBezeichnerText`, `VerkehrsmittelNummer`, `LinienText`, `ProduktID`, `VonRichtungsText`, `RichtungsID`, `RichtungsText`, `FahrtspezialText`, `LinienfahrwegID`, `Zugname`, `VerkehrsmittelID`, `PrognoseUngenau`, `StoerungsInfo`, `FahrradMitnahme`, `FahrzeugTypID`, `Auslastungsstufe`, `ServiceAttribut`, `IstFormation`, `FahrtBeziehung`, `HaltestellenName`, `Einsteigeverbot`, `Aussteigeverbot`, steig and sector texts, `Via`, `IstAnkunftDisposition`, `IstAbfahrtDisposition`, `IstAnkunftPrognoseUngenau`, `IstAbfahrtPrognoseUngenau`, `IstAnkunftPrognoseQualitaet`, `IstAbfahrtPrognoseQualitaet`.

## Helper Method Rules

- Boolean parsing: only `true` (case-insensitive, trimmed) maps to `True`.
- Datetime parsing: ISO 8601 with optional fractional seconds, `Z` or offset; invalid values return `None` and log a warning.
- Event timestamp: earliest of arrival/departure when both exist.
- Filter matching: pattern list is comma-separated after trimming; `*` matches any number of any characters; full-match semantics.

## Runtime Metric

- Total transform wall-clock runtime is exposed in milliseconds.
- Runtime is recorded even if all journeys are filtered out.

### Envelope and Protocol

23. Handling of `Bestaetigung/@Ergebnis` other than `ok`, `WeitereDaten=true`, the poll protocol (`DatenBereitAnfrage`, `DatenAbrufenAnfrage`), `AboID` mapping, and the subscription parameters `Hysterese`, `Vorschauzeit`, `MitRealZeiten`, and `NurAktualisierung` belong to the datasource and are not specified here.
24. With `MitRealZeiten=false` real times may arrive late or never (chapter 6.1.9). The transformer cannot detect this.
