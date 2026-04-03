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
  - `token`: Optional access token to grant access to the GTFS-RT feed
  - `dialect`: Regional implementation variant for parsing the SIRI data (required)
  - `filter`: Filter on ParticipantRef. Multiple participant refs can be separated by comma

### 3. SIRI SX Adapter (`sirisx`)
- **Purpose:** Handle communication to a SIRI-SX server to import alerts from there.
- **Config options:**
  - `endpoint`: URL of the SIRI Lite endpoint. The placeholder {requestorRef} will be replaced by the value of `requestorref` (required)
  - `requestorref`: Requestor reference commited with the agency running the SIRI SX server (required)
  - `method`: Data requesting method. Currently only `request/response` is supported (required)
  - `dialect`: Regional implementation variant for parsing the SIRI data (required)
  - `filter`: Filter on ParticipantRef. Multiple participant refs can be separated by comma

## Adding/Editing Adapters
- Go to **Settings > Sources**
- Select the adapter type and fill in the configuration fields
- Save and enable the source
