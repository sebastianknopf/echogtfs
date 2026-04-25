# Adapters & Configuration

EchoGTFS uses adapters to connect to various data sources. Each adapter has specific configuration options.

## Period Type Support

All adapters distinguish between two types of time periods for service alerts:

- **Impact Period (Gültigkeitszeitraum)**: Specifies when services are actually affected by the disruption
- **Communication Period (Veröffentlichungszeitraum)**: Specifies when the alert should be communicated to users

**Storage & Behavior:**
- Both period types are stored as separate entries in the database with their respective `period_type`
- An alert can have multiple periods of each type
- **OpenBegin periods** (no start time) are always imported, regardless of their end time
- **OpenEnd periods** (no end time) never expire, regardless of their start time

**Import Filtering:**
All adapters apply the following filters during import:

1. **Future Alerts Filter**
   - Alerts starting more than 30 days in the future are filtered out
   - Uses the **earliest start time** across **all period types**
   - OpenBegin alerts are always imported

2. **Expired Alerts Filter**
   - Alerts with all periods ended in the past are filtered out
   - Uses the **latest end time** across **all period types**
   - OpenEnd alerts never expire

**Example Scenarios:**
- Alert with impact_period (ended yesterday) and communication_period (ends tomorrow) → **imported** (communication still active)
- Alert with impact_period (start: none, end: +60 days) → **imported** (OpenBegin)
- Alert with impact_period (start: -1 day, end: none) → **imported** (OpenEnd, never expires)

## Available Adapters

### 1. GTFS-RT Adapter (`gtfsrt`)
- **Purpose:** Import real-time alerts from a GTFS-RT ServiceAlerts feed.
- **Config options:**
  - `endpoint`: URL of the GTFS-RT feed (required)
  - `token`: Optional access token to grant access to the GTFS-RT feed

#### GTFS-RT Protocol Fields

The adapter supports the extended GTFS-Realtime specification with the following period fields in the protobuf `Alert` message:

- **`impact_period`** (repeated TimeRange): Service impact periods → stored as **impact_period**
- **`communication_period`** (repeated TimeRange): Publication periods → stored as **communication_period**
- **`active_period`** (repeated TimeRange, deprecated): Legacy field for backward compatibility → treated as **impact_period** if new fields are absent

**Parsing Priority:**
1. Parse all `impact_period` fields as impact periods
2. Parse all `communication_period` fields as communication periods
3. If neither field is present, parse `active_period` fields as impact periods (backward compatibility)

The adapter follows the general Period Type Support and Alert Filtering rules described above.

### 2. SIRI Lite Adapter (`sirilite`)
- **Purpose:** Import alerts from a SIRI Lite endpoint.
- **Config options:**
  - `endpoint`: URL of the SIRI Lite endpoint (required)
  - `token`: Optional access token to grant access to the SIRI feed
  - `dialect`: Regional implementation variant for parsing the SIRI data (required)
  - `filter`: Filter on ParticipantRef. Multiple participant refs can be separated by comma

**Available Dialects:**
- **`swiss`**: Swiss public transport SIRI-Lite implementation
- **`sirisx`**: SIRI-SX dialect for generic SIRI-SX feeds

#### SIRI XML Elements

Both SIRI Lite and SIRI SX adapters parse the following XML elements from `PtSituationElement`:

- **`<ValidityPeriod>`**: Service impact period → stored as **impact_period**
  - `<StartTime>`: Impact start time
  - `<EndTime>`: Impact end time
  
- **`<PublicationWindow>`**: Alert publication period → stored as **communication_period**
  - `<StartTime>`: Publication start time
  - `<EndTime>`: Publication end time

**Parsing Behavior:**
- Both element types can appear multiple times and all are parsed
- Each `ValidityPeriod` creates one impact_period entry
- Each `PublicationWindow` creates one communication_period entry
- The adapter follows the general Period Type Support and Alert Filtering rules described above
- Additionally, `PublicationWindow` is used for import-time filtering to exclude alerts outside their publication window

**Example:**
```xml
<PtSituationElement>
  <ValidityPeriod>
    <StartTime>2026-04-08T12:00:00Z</StartTime>
    <EndTime>2026-06-19T21:00:00Z</EndTime>
  </ValidityPeriod>
  <PublicationWindow>
    <StartTime>2026-04-08T12:00:00Z</StartTime>
    <EndTime>2026-06-19T21:10:00Z</EndTime>
  </PublicationWindow>
  ...
</PtSituationElement>
```
Result: Two separate periods with one impact_period (12:00-21:00) and one communication_period (12:00-21:10)

### 3. SIRI SX Adapter (`sirisx`)
- **Purpose:** Handle communication to a SIRI-SX server to import alerts from there.
- **Config options:**
  - `endpoint`: URL of the SIRI-SX endpoint. The placeholder {participantRef} will be replaced by the value of `participantref` (required)
  - `participantref`: Participant reference commited with the agency running the SIRI SX server (required)
  - `method`: Data requesting method. Currently only `request/response` is supported (required)
  - `dialect`: Regional implementation variant for parsing the SIRI data (required)
  - `filter`: Filter on ParticipantRef. Multiple participant refs can be separated by comma

**Available Dialects:**
- **`sirisx`**: Generic SIRI-SX implementation

**Note:** The SIRI SX adapter uses the same SIRI XML element parsing as SIRI Lite (see above).

## SIRI Adapter Data Extraction

Both SIRI Lite and SIRI SX adapters use a hierarchical fallback mechanism to extract informed entities (affected routes, stops, and trips) from SIRI XML.

### Entity Extraction Hierarchy

All SIRI adapters extract informed entities from `Affects` elements using the following fallback hierarchy:

1. **PublishingActions > PublishAtScope > Affects** (primary)
   - Searches within `<PublishingAction>` elements for `<PublishAtScope><Affects>`
   - Used when alerts specify publishing scope

2. **Consequences > Consequence > Affects** (fallback)
   - If no Affects found in PublishingActions, searches within `<Consequence>` elements
   - Used when alerts specify consequences/impacts

3. **Affects on PtSituationElement** (last fallback)
   - If no Affects found in Consequences, uses `<Affects>` directly at PtSituationElement level
   - Used for simple alert structures

**Early Exit:** Once Affects elements are found at any level, lower levels are not searched.

### Extracted Entity Types

From each `Affects` element, the following entities are extracted:

#### Networks & Routes
- **AffectedNetwork > AffectedLine**
  - `LineRef` → `route_id`
  - `OperatorRef` → `agency_id`

#### Stops
- **AffectedStopPlace** or **AffectedStopPoint**
  - `StopPlaceRef` or `StopPointRef` → `stop_id`
  - Can also include `AffectedLine` within stop → creates combined stop+route entities

#### Vehicle Journeys (Trips)
- **VehicleJourneys > AffectedVehicleJourney**
  - `VehicleJourneyRef` or `DatedVehicleJourneyRef` → `trip_id` (with fallback: tries VehicleJourneyRef first, then DatedVehicleJourneyRef)
  - `OperatorRef` → `agency_id`
  - `Route > StopPoints > AffectedStopPoint > StopPointRef` → `stop_id`
  - **Note:** All trip-based entities are marked as `is_valid=False` by default and depend on the configured Invalid Reference Policy

### Swiss Dialect Specifics

The **Swiss** dialect (`sirilite` adapter with `dialect: swiss`) follows these additional rules:

- **Publication Window Filtering:** Alerts outside their `PublicationWindow` are filtered out
- **Participant Reference Filtering:** Respects `filter` config for `ParticipantRef`
- **Text Extraction:** 
  - Extracts from `PassengerInformationAction` with perspective "general"
  - Supports `TextualContent` with size "L" (large), "M" (medium), "S" (small)
  - Falls back to direct `Summary`/`Detail` elements on `PtSituationElement`
- **HTML Stripping:** Automatically removes HTML tags and entities from text content
- **Language Fallback:**
  1. `xml:lang` attribute on text element
  2. `<Language>` element on PtSituationElement
  3. System locale
  4. Default: `de`

### SIRI-SX Dialect Specifics

The **SIRI-SX** dialect (`sirilite` adapter with `dialect: sirisx` or standalone `sirisx` adapter) follows these additional rules:

- **Publication Window Filtering:** Alerts outside their `PublicationWindow` are filtered out
- **Participant Reference Filtering:** Respects `filter` config for `ParticipantRef`
- **Text Extraction:**
  - Prioritizes direct `Summary`/`Detail`/`Description` elements on `PtSituationElement`
  - Falls back to `PassengerInformationAction` with perspective "general"
  - Falls back to `TextualContent` with size "L"
  - Also tries `ReasonContent`/`ConsequenceContent`/`DescriptionContent` for descriptions
- **HTML Stripping:** Automatically removes HTML tags and entities from text content
- **Language Fallback:** Same 4-level hierarchy as Swiss dialect
- **Unlimited End Times:** Treats `ValidityPeriod` with year 2500 as unlimited (no end time)

### Trip Reference Validation

All SIRI adapters mark trip-based entities (entities with `trip_id` but no `agency_id`, `route_id`, or `stop_id`) as **invalid** (`is_valid=False`). The behavior depends on the configured **Invalid Reference Policy**:

- **`DISCARD_ALERT`**: Deletes entire alert if any invalid entity found
- **`DISCARD_INVALID`**: Keeps alert, discards all invalid entities
- **`DISCARD_INVALID_ELEMENTS`**: Keeps alert, nullifies invalid fields within entities
- **`KEEP_ALERT`**: Keeps alert and all entities, but deactivates the alert
- **`NOT_SPECIFIED`**: No validation (default for manual alerts)

## Adding/Editing Adapters
- Go to **Settings > Sources**
- Select the adapter type and fill in the configuration fields
- Save and enable the source
