# Configuring Data Sources

EchoGTFS supports multiple data sources for GTFS and real-time alerts.

## Real-Time Data Sources
- Additional alert sources (e.g., SIRI-SX, GTFS-RT) can be configured under **Sources**.
- Each source can be enabled/disabled and configured individually. If a source is disabled, all alerts for this source are removed.

See [Adapters & Configuration](adapters.md) for details on available adapters and their options.

## Managing Sources
- Go to **Sources** to add, edit, or remove data sources.
- Each source requires a name, type (adapter), and configuration parameters.
- The cron expression defines the runtime profile for the data source. The data source is executed according to the cron expression.

## Executing Sources
- Go to **Sources** and hit the run button. 

This triggers the sync process on the server asynchronously. This is especially helpful after changing some parameters to trigger an import immediately.

## Mapping
Most times, the IDs of external data sources do not match the GTFS static data. To adapt those data, mappings for **Agencies**, **Routes** and **Stops** can be defined. 

Each mapping consists of a key and a corresponding value. The keys can also use `*` as wildcard to map multiple variant IDs to one single ID in the GTFS static feed.

### Invalid Reference Handling Policies

When mapping external data to GTFS static data, it is possible that some references (e.g., agency, route, or stop IDs) cannot be resolved, even after applying the defined mappings. EchoGTFS provides policies to handle these invalid references:

- **Not Specified** Alerts are not handled in a special way and published as-they-are. This may lead to incosistent IDs between the GTFS-RT feed and the GTFS static feed.
- **Discard Alerts** Alerts with at least one invalid reference are discarded completely.
- **Discard Invalid References** References with invalid elements (remember: a reference can contain for example a stop_id and a route_id at the same time) are discarded. If the alert has no valid references afterwards, the alert is saved but disabled.
- **Discard Invalid Reference Elements** Invalid reference elements (a single stop_id or route_id of a reference) are discarded but the reference itself is kept, as long it has at least one valid element. If the alert has no valid references afterwards, the alert is saved but disabled.
- **Disable Alerts** Alerts with at least one invalid reference are saved but disabled.

The chosen policy affects how the system handles mismatches between external data and the static GTFS feed.

## Enrichments

Enrichments allow automatic extraction of `cause`, `effect`, and `severity` values from alert text fields (header and/or description). This is useful when external data sources provide alerts with unclear or generic metadata, but include meaningful information in the text.

### Purpose and Use Cases

Enrichments are particularly valuable when:
- External alerts have `UNKNOWN_CAUSE`, `UNKNOWN_EFFECT`, or `UNKNOWN_SEVERITY` as default values
- Important information (e.g., "strike", "construction", "severe disruption") is only present in the alert text
- You want to improve the quality of GTFS-RT feeds by deriving structured metadata from unstructured text
- Multiple data sources use different terminology that needs to be normalized

### How Enrichments Work

#### Configuration
For each data source, you can define enrichment rules with the following properties:

1. **Enrichment Type:** What to extract
   - `cause` – Extract alert cause (e.g., STRIKE, CONSTRUCTION, WEATHER)
   - `effect` – Extract alert effect (e.g., NO_SERVICE, SIGNIFICANT_DELAYS)
   - `severity` – Extract severity level (e.g., SEVERE, WARNING, INFO)

2. **Source Field:** Where to search
   - `Header` – Search only in alert header text
   - `Description` – Search only in alert description text
   - `Header/Description` – Search in both fields

3. **Pattern (Key):** Text pattern to match (see matching rules below)

4. **Value:** The value to assign when the pattern matches (must be a valid enum value)

#### Matching Rules ("Regex-Light")

Enrichment patterns use a simplified matching system:

- **Case-insensitive:** "streik", "STREIK", and "Streik" are treated identically
- **Wildcard support:** `*` matches any characters (e.g., `linie*5` matches "Linie 5", "Linie 15", "Linie 555")
- **Implicit wildcards:** Patterns are automatically wrapped with wildcards at start and end
  - Pattern `streik` matches "wegen Streik morgen" and "Streik auf Linie 5"
- **AND conditions:** Comma-separated values must all be present
  - Pattern `streik,berlin` only matches if both "streik" AND "berlin" appear in the text
  - Pattern `ausfall,linie,5` matches only if all three terms are found

#### Processing Logic

1. Enrichments are processed in **priority order**
2. For each alert, enrichments are applied **only if the current value is a default/unknown value**:
   - For `cause`: Only if current value is `UNKNOWN_CAUSE` or `OTHER_CAUSE`
   - For `effect`: Only if current value is `UNKNOWN_EFFECT` or `OTHER_EFFECT`
   - For `severity`: Only if current value is `UNKNOWN_SEVERITY` or `INFO`
3. **First match wins:** Once an enrichment matches for a specific type (cause/effect/severity), no further enrichments of that type are applied to that alert
4. All translations (all languages) are searched for matches

### Example Configuration

Suppose you have a data source that always sets `cause=UNKNOWN_CAUSE` and `effect=UNKNOWN_EFFECT`, but provides useful text:

**Enrichment Rules:**
```
1. Type: cause,   Field: Header, Pattern: "streik",           Value: STRIKE,       Sort: 1
2. Type: cause,   Field: Header, Pattern: "bauarbeiten",     Value: CONSTRUCTION, Sort: 2
3. Type: effect,  Field: Both,   Pattern: "ausfall,linie",   Value: NO_SERVICE,   Sort: 3
4. Type: effect,  Field: Both,   Pattern: "verspätung*",     Value: SIGNIFICANT_DELAYS, Sort: 4
5. Type: severity, Field: Desc,  Pattern: "schwer*störung", Value: SEVERE,       Sort: 5
```

**Input Alert:**
- Header: "Streik am Montag"
- Description: "Ausfall mehrerer Linien wegen schwerer Störung"
- Initial: `cause=UNKNOWN_CAUSE, effect=UNKNOWN_EFFECT, severity=INFO`

**Result after Enrichment:**
- `cause=STRIKE` (matched rule 1: "streik" in header)
- `effect=NO_SERVICE` (matched rule 3: "ausfall" AND "linie" in description)
- `severity=SEVERE` (matched rule 5: "schwer" in description, followed by any characters, then "störung")

### Best Practices

- **Start with high-priority, specific patterns** (e.g., "streik,hauptbahnhof" before just "streik")
- **Use AND conditions** (commas) to avoid false positives
- **Test patterns** with real alert data from your sources
- **Combine with mappings:** Enrichments work independently from ID mappings and are applied after data is fetched but before validation

## Monitoring and Logging

EchoGTFS automatically logs all requests to external data sources. This helps with:
- **Debugging:** Inspect raw responses when alerts don't import correctly
- **Monitoring:** Track HTTP status codes and identify failing sources
- **Analysis:** Compare response sizes over time to detect API changes

### Quick Access

1. Go to **Sources** in the main navigation
2. Click the **document icon** next to any data source
3. View the most recent log entries with timestamps, endpoints, status codes, and response sizes

### Error Indicators

- **ERROR badge (red):** Shown when the last request returned a 4xx or 5xx status code
- Helps quickly identify problematic data sources

### What's Logged

- Complete request and response data (including headers)
- HTTP status codes
- Response sizes (actual uncompressed size)
- Execution timestamps

For detailed information about log interpretation, troubleshooting, and technical details, see the [Data Source Logging](logging.md) documentation.
