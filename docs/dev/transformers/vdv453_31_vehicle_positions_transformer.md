# VDV453 3.1 Vehicle Positions Transformer

## Concept Mapping

| VDV453 VIS | SIRI-VM equivalent | Internal field |
| --- | --- | --- |
| `VISNachricht` | `VehicleMonitoringDelivery` | none |
| `VISFahrplanlage` | `VehicleActivity` | one vehicle-position record or one deletion record |
| `VISMeldungsart` | `VehicleStatus` / `Monitored` | position record or deletion record |
| `FahrtID/FahrtBezeichner` | `DatedVehicleJourneyRef` | `trip.trip_id` |
| `FahrtID/Betriebstag` | `DataFrameRef` | `trip.start_date` |
| `LinienID` | `LineRef` | `trip.route_id` |
| `FahrtInfo/FahrzeugID` | `VehicleRef` | `vehicle_id`, `vehicle_label` |
| `Longitude`, `Latitude` | `VehicleLocation` | `longitude`, `latitude` |
| `Zst` | `RecordedAtTime` | `timestamp` |
| `VerfallZst` | `ValidUntilTime` | validity check |
| `PrognoseMoeglich` | `Monitored` | filter and deletion |
| `AufHst` | `VehicleAtStop` | `current_status` |
| `AktHaltID` / `NachHaltID` | `MonitoredCall/StopPointRef` | `stop_id` |
| `FahrtInfo/BetreiberID` | `OperatorRef` | operator filter |
| `FahrtInfo/AbfahrtszeitStartHst`, `AnkunftszeitZielHst` | `OriginAimedDepartureTime`, `DestinationAimedArrivalTime` | `scheduled_start_time`, `scheduled_end_time` (no stop IDs) |

VDV453 VIS differs from SIRI-VM in these points, which shape the rules below:

- A delivery is differential. Only changed vehicles are transmitted. A vehicle that is not in a delivery is still on the road until a removal message or its `VerfallZst` arrives (chapter 6.4.3.1).
- Removal is an explicit message type. `VISMeldungsart` other than `Fahrplanlage` means that the vehicle must be removed from the display.
- There is no call list. VIS transmits the current stop (`AktHaltID`), the next stop (`NachHaltID`), and the progress between them (`Distanz`). There are no aimed times per stop and no `PreviousCalls` / `OnwardCalls`.
- Coordinates are integers in WGS-84 milliseconds of arc, not decimal degrees.
- Times are UTC unless an offset is given (chapter 6.1.2).
- `FahrtBezeichner` is unique only in the scope of the `Betriebstag` (chapter 6.1.5).
- `VISID` selects a visualization area (an abstract subset of all vehicles). It is a subscription parameter and not a property of a vehicle.
- `BetreiberID`, `FahrzeugID`, and all schedule anchors live inside the optional `FahrtInfo` element.

## Input and Entry Points

1. The datasource passes XML root data to `transform()` as `{"root": xml_root, ...}`. The root is a `DatenAbrufenAntwort` element.
2. `transform()` scans for `VISFahrplanlage` elements inside `VISNachricht` elements. Element names are not namespace-qualified.
3. Each `VISFahrplanlage` is parsed independently and converted to one record, either a vehicle position or a deletion.
4. `Bestaetigung`, `WeitereDaten`, `VISNachricht/@AboID`, `VISID`, and `Protokolleintrag` are not evaluated by the transformer. A `VISNachricht` without `VISFahrplanlage` (no vehicle in the area) produces no records.

## Data Source Requirement

VIS is a differential feed. The data source must run with `is_differential_updates = true` (see [differential-incremental.md](../differential-incremental.md)). Without it, every vehicle that is missing from a delivery would be deleted by the absence-based deletion, although it is still on the road. Removal is signalled with `is_deleted` records only.

## Top-Level Transform Flow

1. Reset runtime metric (`_runtime_duration_ms = 0.0`) and start a timer with `perf_counter()`.
2. Read all `VISFahrplanlage` nodes. If none are present, return an empty list.
3. For each node, branch on `VISMeldungsart`:
   - `Fahrplanlage`: call `_parse_vehicle_activity()`. A `None` result counts as filtered. A record is appended to the output.
   - `Fahrtabbruch`, `RegulaeresFahrtende`, `BereichVerlassen`: call `_build_deletion_record()` and append the result. Filters and freshness checks are skipped.
   - Missing or unknown value: count as filtered and log a warning.
4. A parsing exception is logged as an error and processing continues with the next node.
5. Return the records in delivery order. Log processed and filtered counts.
6. Always store the elapsed runtime in milliseconds in `_runtime_duration_ms` (via `finally`).

Records are returned in delivery order. The transformer does not deduplicate vehicles.

## Filtering

The datasource parses the configured filter, using commas or whitespace as separators, into the transformer's `line`, `operator`, and `legacy` pattern lists. Unprefixed values and `operator/` values filter `FahrtInfo/BetreiberID`. `line/` values filter `LinienID`.

`*` matches any number of characters, and matching covers the complete value (`re.fullmatch` after escaping literals and replacing `*` with `.*`). A configured operator or line filter rejects an activity when the corresponding element is missing or does not match any configured pattern. `RichtungsID` is not filtered.

Filters apply to `Fahrplanlage` messages only. Removal messages bypass them: deleting an entity that was never stored is not an error (see [transformation.md](../transformation.md)), and `BetreiberID` can be missing in any message because `FahrtInfo` is optional.

## Activity-Level Filtering Rules

A `VISFahrplanlage` with `VISMeldungsart = Fahrplanlage` is discarded (`None`) when any of these conditions is true. The conditions are evaluated in this order.

1. `VerfallZst` is present and is in the past. The attribute is required by the schema, a missing value is treated as not expired.
2. `Zst` is present and older than 5 minutes.
3. Configured operator filter is set and `FahrtInfo/BetreiberID` is missing or does not match any configured pattern.
4. Configured line filter is set and `LinienID` is missing or does not match any configured pattern.
5. `PrognoseMoeglich` is `false`. This is handled as a removal, see [Real-Time Availability](#real-time-availability).
6. `FahrtID/FahrtBezeichner` (`trip_id`) is missing or empty.
7. `LinienID` (`route_id`) is missing or empty.
8. No `vehicle_id` can be resolved, see [Vehicle Identity](#vehicle-identity).
9. `Longitude` or `Latitude` is missing.
10. `Longitude` or `Latitude` is not an integer, or the converted degree value is out of range.

Both coordinates are optional in the schema, because VIS can also feed a vehicle list without a map. A vehicle without a position cannot be exported as a vehicle position and is therefore discarded (rule 9), the same as in SIRI-VM.

## Real-Time Availability

`PrognoseMoeglich` is a required element and corresponds to the SIRI `Monitored` flag. With `false`, the producer has no real-time information for the vehicle, and position and delay must be considered outdated (chapter 6.4.3.3.1).

- `PrognoseMoeglich = false` does not create a position record.
- Because VIS is differential, an earlier position of the same vehicle is still stored and would remain on the map until `VerfallZst`. The transformer therefore returns a deletion record for the vehicle, see [Deletion Records](#deletion-records).
- `PrognoseMoeglich` missing counts as `true`.

`PrognoseUngenau` (inaccurate forecast) does not affect the position and is ignored.

## Field Extraction Rules

### Core Trip and Vehicle Fields

- `trip.trip_id` from `FahrtID/FahrtBezeichner`.
- `trip.start_date` from `FahrtID/Betriebstag`, as delivered (`YYYY-MM-DD`). If `Betriebstag` is missing, it falls back to the local date of `scheduled_start_time`; otherwise an empty string.
- `trip.start_time` is derived from `scheduled_start_time` in the configured time zone (`settings.timezone`) as `HH:MM:SS`, in the same way as in the VDV454 transformer ([vdv454_31_trip_updates_transformer.md](vdv454_31_trip_updates_transformer.md)). If the local start lies on the day after `start_date`, 24 is added to the hours (for example `25:10:00`). Without a start time it is an empty string.
- `trip.route_id` from `LinienID`.
- `latitude` and `longitude` from `Latitude` and `Longitude`, see [Coordinate Conversion](#coordinate-conversion).

### Vehicle Identity

1. `vehicle_id` is `FahrtInfo/FahrzeugID` when present and not empty. `vehicle_label` is the same value.
2. Otherwise `vehicle_id` is `<Betriebstag>|<FahrtBezeichner>` and `vehicle_label` is `None`. `FahrzeugID` is optional in the schema, and many producers omit `FahrtInfo`. Without a fallback, these feeds would deliver no vehicles at all. `FahrtBezeichner` is only unique per `Betriebstag`, so both parts are combined.
3. If neither rule yields a value, the activity is discarded.

The same resolution is used for deletion records, so that a removal addresses the entity created by the position record. A producer that transmits `FahrzeugID` only in some messages of a vehicle can break this link. The deletion record therefore also carries the trip reference, see [Deletion Records](#deletion-records).

### Coordinate Conversion

`Longitude` and `Latitude` are integers in WGS-84 milliseconds of arc (chapter 6.4.3.3.1).

- `degrees = value / 3600000`.
- Longitude must be within -180 to 180, latitude within -90 to 90. Values outside the range discard the activity.
- Example from the specification: `Longitude = 48015918` gives `13.3378`, `Latitude = 189028512` gives `52.5079`.

The values are converted to `float`. Whitespace is trimmed before parsing. Decimal values are rejected, because the schema type is `xsd:integer`.

### Current Stop Status

`AktHaltID` is the current or last stop. `NachHaltID` is the next stop. `AufHst = true` means that the vehicle is currently at `AktHaltID`.

| Condition | `current_status` | `stop_id` |
| --- | --- | --- |
| `AufHst = true` and `AktHaltID` present | `STOPPED_AT` | `AktHaltID` |
| `AufHst` is not `true` and `NachHaltID` present | `IN_TRANSIT_TO` | `NachHaltID` |
| `AufHst` is not `true`, only `AktHaltID` present | `IN_TRANSIT_TO` | not set |
| `AufHst = true`, no `AktHaltID` | `IN_TRANSIT_TO` | not set |

- This follows GTFS-Realtime semantics, where `stop_id` is the stop the vehicle is stopped at or heading to. It matches SIRI-VM, where `MonitoredCall` is the next or current stop.
- `stop_id` is the value of `HaltID/HaltestellenID`. `BereichsID` and `SteigID` are not used, in line with the VDV454 transformer.
- `current_stop_sequence` is not set and defaults to 0. `AktHstSeqZaehler` and `NachHstSeqZaehler` are the pass-through order for stub journeys (chapter 6.4.3.3.1), not the position in the stop sequence, so they must not be mapped to the SIRI `Order` equivalent.
- `Distanz` (percentage between current and next stop) has no counterpart in the internal model and is ignored.

### Schedule Anchors and Completeness

VIS carries no call list and no nominal time for the current or next stop. `StartHstnameKurz` and `ZielHstnameKurz` are short display names, not stop identifiers, so they are not used as stop IDs. The only schedule information is the time pair in `FahrtInfo`. The matching service accepts start and end times without stop IDs (see [matching.md](../matching.md), Start/End Anchor Matching).

- `scheduled_start_time` from `FahrtInfo/AbfahrtszeitStartHst`.
- `scheduled_end_time` from `FahrtInfo/AnkunftszeitZielHst`.
- `scheduled_start_stop_id` and `scheduled_end_stop_id` are always `None`.
- `scheduled_intermediate_stops` is always empty. `AktHaltID` and `NachHaltID` are not used as intermediate stops, because VIS provides no nominal time for them and the estimated time of the vehicle must not be used as nominal time.

Rules per completeness mode:

1. `is_complete_stop_sequence = true` when `AbfahrtszeitStartHst` is present and parseable. `scheduled_start_time` is set, `scheduled_end_time` is set when `AnkunftszeitZielHst` is present and parseable, otherwise `None`. The start time is required because the matching stage runs only with a start time.
2. Otherwise `is_complete_stop_sequence = false` and both times are `None`, even if `AnkunftszeitZielHst` was present.
3. A missing or incomplete `FahrtInfo` never discards the activity. The vehicle is kept and can still be assigned by trip ID (`DIRECT_BY_ID`) after identifier mapping.

Unlike SIRI-VM, an incomplete anchor set is not a discard reason. SIRI-VM discards activities that claim a complete stop sequence without usable call times. VIS has no such claim, so the transformer decides the mode itself.

## Timestamp Resolution

1. `timestamp` is `Zst`. It is required by the schema and is the time of data creation.
2. If `Zst` is missing or unparseable, use `VerfallZst` when present.
3. Otherwise use the current UTC time (`datetime.now(timezone.utc)`).

All timestamps follow chapter 6.1.2: a value without offset is UTC, `Z` and offsets are converted to UTC. This differs from the SIRI-ET transformer, which uses the configured timezone for naive values. Fractions of a second are accepted and kept.

## Deletion Records

A deletion record is returned instead of a position in these cases:

| Source | Meaning |
| --- | --- |
| `VISMeldungsart = Fahrtabbruch` | Trip ended off schedule. The optional `FahrtAbbruchUrsacheText` is ignored. |
| `VISMeldungsart = RegulaeresFahrtende` | Trip ended regularly. Counterpart of SIRI `VehicleStatus = completed`, which SIRI-VM discards. |
| `VISMeldungsart = BereichVerlassen` | Vehicle left the visualization area. |
| `VISMeldungsart = Fahrplanlage` and `PrognoseMoeglich = false` | Position is outdated. |

Record shape:

```python
{
    "vehicle_id": str,
    "is_deleted": True,
    "trip": {"trip_id": str},
}
```

- `vehicle_id` uses the rules of [Vehicle Identity](#vehicle-identity). If it cannot be resolved, the record is built from the trip reference alone and `vehicle_id` is omitted.
- `trip.trip_id` is `FahrtID/FahrtBezeichner`. The processing service uses it to find a vehicle that was stored with a matched trip ID (see [differential-incremental.md](../differential-incremental.md), Explicit Deletion via `is_deleted`).
- If neither `vehicle_id` nor `trip_id` can be resolved, no record is returned and the message counts as filtered.
- Deletion records are not parsed further. They bypass operator filter, line filter, `Zst` age check, and `VerfallZst` check, because a late removal message must still remove the vehicle.
- Deletion semantics (scope per data source, ignored outcome, no double deletion) are defined in [transformation.md](../transformation.md).

`BereichVerlassen` refers to the visualization area of one subscription. If several subscriptions (`VISID`) of the same data source overlap, a vehicle that leaves one area can still be in another. The transformer cannot detect this, because `VISID` is not evaluated. Overlapping areas in one data source are therefore not supported.

## Returned Data Shape

Each parsed position record contains both nested and top-level scheduled fields, the same as SIRI-VM.

- Nested trip object (`trip`):
  - `trip_id`, `start_time`, `start_date`, `route_id`
  - `schedule_relationship = "SCHEDULED"`
  - `assignment_type = "ASSIGNED"`
  - `is_active = True`
  - `is_complete_stop_sequence`
  - `scheduled_start_stop_id` (`None`), `scheduled_start_time`
  - `scheduled_end_stop_id` (`None`), `scheduled_end_time`
  - `scheduled_intermediate_stops` (always empty)

- Top-level vehicle object:
  - `is_deleted = False`
  - `vehicle_id`, `vehicle_label`
  - `vehicle_wheelchair_accessible = UNKNOWN`
  - `timestamp`, `latitude`, `longitude`
  - `current_stop_sequence` (omitted, consumer default 0), `current_status`, `stop_id` (only when resolved)
  - `congestion_level = UNKNOWN_CONGESTION_LEVEL`
  - Duplicated schedule anchor fields (`scheduled_*`) for vehicle-level consumers.

Fields not listed are set by the consumer. For the normalized contract consumed by sync processing, see [transformation.md](../transformation.md).

## Elements Not Extracted

These elements have no counterpart in the internal vehicle-position model and are ignored: On `VISFahrplanlage` level: `Protokolleintrag`, `VISID`, `LinienText`, `RichtungsID`, `RichtungsText`, `VonRichtungsText`, `Verspaetung`, `StartHstnameKurz`, `EndHstnameKurz`, `AktHstnameKurz`, `NachHstnameKurz`, `AktHstSeqZaehler`, `NachHstSeqZaehler`, `Distanz`, `Geschwindigkeit`, `KompassRichtung`, `PrognoseUngenau`, `FahrtAbbruchUrsacheText`, `Auslastungsstufe`.

In `FahrtInfo`: `LinienNr`, `VerkehrsmittelNummer`, `UmlaufNr`, `KursNr`, `StartHstnameLang`, `StartHstnameKurz`, `ZielHstnameLang`, `ZielHstnameKurz`, `LinienfahrwegID`, `ProduktID`, `AusfuehrenderID`, `Direktruf`, `VerkehrsmittelID`, `ServiceAttribut`. Only `FahrzeugID`, `BetreiberID`, `AbfahrtszeitStartHst`, and `AnkunftszeitZielHst` are evaluated.

`Geschwindigkeit`, `KompassRichtung`, and `Auslastungsstufe` carry useful data, but the internal vehicle-position contract has no fields for speed, bearing, or occupancy, and SIRI-VM does not extract them either. Extending the contract is a change of [transformation.md](../transformation.md) and of the export, not of this transformer.

## Helper Method Rules

- `_get_text(element)`: trims text, returns `None` for missing or empty values.
- `_parse_bool(value, default=...)`: only the string `"true"` (case-insensitive, trimmed) maps to `True`; all other non-`None` values map to `False`. `xsd:boolean` also allows `1` and `0`, which are accepted as `True` and `False` here.
- `_parse_datetime(value)`: parses ISO 8601 including `Z` suffix replacement to `+00:00` and optional fractional seconds; invalid values return `None` and emit a warning.
- `_to_utc(value)`: treats naive datetimes as UTC; timezone-aware values are converted to UTC.
- `_parse_coordinate(value, limit)`: parses the integer, divides by 3600000, and returns `None` with a warning when the value is not an integer or exceeds `limit` degrees.
- `_resolve_stop_id(halt_id)`: returns the trimmed `HaltestellenID` or `None`.
- Filter matching: pattern list is comma-separated after trimming; `*` matches any number of any characters; full-match semantics.

## Runtime Metric

- `get_runtime_duration_ms()` returns wall-clock runtime measured around the full `transform()` call.
- The runtime metric is available even when parsing returns early or encounters per-activity errors.

## Envelope and Protocol

The following topics belong to the datasource and are not specified here:

- The poll protocol (`AboAnfrage` with `AboVIS`, `DatenBereitAnfrage`, `DatenAbrufenAnfrage`) and the mapping of `AboID`.
- Handling of `Bestaetigung/@Ergebnis` other than `ok` and of `WeitereDaten = true`, which requires repeated `DatenAbrufenAnfrage` requests until all data is received.
- The subscription parameters `VISID` and `LinienFilter` (a server-side filter of lines and directions). A server-side `LinienFilter` reduces transfer volume, the transformer filters still apply on top.
- A subscription that ends (`VerfallZst` of the `AboVIS`) leaves the last known vehicles stored. They are removed by the cleanup service (vehicles not updated within the configured maximum age) or by a later removal message.
