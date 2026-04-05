# Adapters & Configuration

EchoGTFS uses adapters to connect to various data sources. Each adapter has specific configuration options.

## Available Adapters

### 1. GTFS-RT Adapter (`gtfsrt`)
- **Purpose:** Import real-time alerts from a GTFS-RT ServiceAlerts feed.
- **Config options:**
  - `endpoint`: URL of the GTFS-RT feed (required)
  - `token`: Optional access token to grant access to the GTFS-RT feed

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
