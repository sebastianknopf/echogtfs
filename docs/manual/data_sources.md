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

#### Invalid Reference Handling Policies

When mapping external data to GTFS static data, it is possible that some references (e.g., agency, route, or stop IDs) cannot be resolved, even after applying the defined mappings. EchoGTFS provides policies to handle these invalid references:

- **Not Specified** Alerts are not handled in a special way and published as-they-are. This may lead to incosistent IDs between the GTFS-RT feed and the GTFS static feed.
- **Discard Alerts** Alerts with at least one invalid reference are discarded completely.
- **Discard Invalid References** References with invalid elements (remember: a reference can contain for example a stop_id and a route_id at the same time) are discarded. If the alert has no valid references afterwards, the alert is saved but disabled.
- **Discard Invalid Reference Elements** Invalid reference elements (a single stop_id or route_id of a reference) are discarded but the reference itself is kept, as long it has at least one valid element. If the alert has no valid references afterwards, the alert is saved but disabled.
- **Disable Alerts** Alerts with at least one invalid reference are saved but disabled.

The chosen policy affects how the system handles mismatches between external data and the static GTFS feed.
