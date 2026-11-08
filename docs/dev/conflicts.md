# Conflicts View and Endpoints

## Access and Frontend Flow

The sidebar entry in [frontend/index.html](../../frontend/index.html) is marked poweruser-only. The [conflicts module](../../frontend/js/conflicts.js) also checks for the `POWERUSER` or `ADMIN` role before loading data.

1. The module requests conflict filter options from `GET /api/conflicts/filters`. The response contains active data sources and every member of the `ConflictType` enum. It restores the selected data source and conflict-type checkboxes from local storage.
2. The selected data source is used for `GET /api/monitoring/conflicts?datasourceId=...`. Type checkboxes filter the returned conflicts in the browser; the monitoring endpoint does not accept a conflict-type filter.
3. The list is ordered newest first. The displayed timestamp uses the browser's local time in `dd.mm.YYYY, HH:mm:ss` format.
4. While the panel is active, it refreshes conflicts every 60 seconds. Changing the data source triggers an immediate request.
5. CSV export sends the selected data source and the selected conflict codes to `GET /api/conflicts/export`.

The selected source is stored under `echogtfs_conflicts_source`. Conflict-type checkbox values are stored under `echogtfs_conflicts_filters`. Unstored types default to checked, unavailable saved types are dropped, and a saved data source that is no longer available is replaced with the first available source.

The filter-options endpoint returns active data sources only. A monitoring response requested without `datasourceId` may also contain internal service-alert conflicts whose `datasource.id` and `datasource.name` are `null`; these cannot match a data source selected in the view.

## Endpoints

The routers are mounted in `backend/src/echogtfs/main.py`. The conflict filter and export routes require `CurrentPoweruser` (an active `POWERUSER` or `ADMIN`). The monitoring route requires `CurrentApiUser` (an active account with the `API` role or higher).

| Method and path | Query parameters | Response |
|---|---|---|
| `GET /api/conflicts/filters` | None | `data_sources` contains active source IDs and names. `conflict_types` contains the numeric code and enum name for each conflict type. |
| `GET /api/monitoring/conflicts` | `datasourceId` (optional) | `{"conflicts": [...]}`; when omitted, conflicts from all sources are returned. |
| `GET /api/conflicts/export` | `datasourceId` (optional); `conflictTypes` (repeatable) | CSV download. Each `conflictTypes` value may be a numeric code or a conflict message. An omitted or empty list exports all conflicts for the requested source. |

Each monitoring conflict has an ID, detection timestamp, numeric `code`, enum-name `message`, a `datasource` object, and a `properties` object. The data source ID and name can be null for conflicts from internal service alerts. Conflict codes and names are defined by `backend/src/echogtfs/enum/conflicts.py`; the filter-options endpoint derives its list from that enum. The frontend classifies codes below `2000` as errors and codes at or above `2000` as warnings.

The CSV header is `ID;Code;Message;DataSourceID;Properties`. The CSV writer uses semicolons and CRLF line endings. After the fixed columns, each conflict's properties are emitted as alternating key and value cells, so rows can have different lengths. Datetime property values use ISO format. The response filename is `conflicts-YYYYMMDD-HHmmss.csv`.

## Conflict Generation

`ConflictExportService.export()` gathers conflicts from data-source logs and the realtime repository. It applies the optional data-source filter, removes duplicate generated IDs, and returns conflicts ordered by timestamp descending.

| Source | Checks |
|---|---|
| Data-source logs | A source with at least five recorded failures produces a data-source failure conflict. |
| Service-alert informed entities | Invalid agency, stop, route, and trip references produce errors. Non-global agency, stop, route, and trip IDs produce warnings. |
| Trip updates and stop events | Invalid stop, route, and trip references produce errors. The service also reports implied `ADDED` or `SKIPPED` stops, corrected stop IDs, non-global stop/route/trip IDs, and departures earlier than arrivals. |
| Vehicle positions | Invalid current stop, route, and trip references produce errors. Non-global current stop, route, and trip IDs produce warnings. A vehicle conflict includes `properties.vehicle_id`, populated using the vehicle display-title order: license plate, label, then vehicle ID. |

Global-ID warnings use the configured global-ID pattern. Vehicle `vehicle_id` itself is not checked as a GTFS entity ID; the vehicle-derived global-ID checks apply to its current stop ID and embedded trip and route IDs.
