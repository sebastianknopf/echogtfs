# GtfsRtServiceAlertsTransformer

## Purpose

This transformer extracts the relevant alert data from a GTFS-Realtime service-alert feed and builds the internal service-alert structure used by EchoGTFS.

## Extraction Rules

- Each GTFS-RT entity is checked to determine whether an alert is present.
- An internal stable ID is generated from the alert ID through the callback function.
- The alert cause is read from the GTFS-RT `cause` field and mapped to the internal cause mapping table.
- The effect is read from the `effect` field and mapped to the internal effect values.
- The severity is read from `severity_level` and mapped to the internal severity table.
- Translations are created from `header_text`, `description_text`, and `url`. Existing languages are preserved, and a fallback translation is generated when needed.
- Active periods are assembled from `impact_period`, `communication_period`, and fallback `active_period` values when present.
- Alerts with a start time far in the future are discarded.
- Alerts with an already expired end time are discarded.
- `informed_entity` entries are converted into agency, route, stop, trip, and direction references.
- If no translations are available, a default text is generated so the alert can still be persisted.
