# EFA-JSON

This specification describes the EFA-JSON data source using the ADDINFO dialect. The registered EFA-JSON data source is currently a placeholder and cannot yet import data.

## Purpose

The EFA-JSON data source is intended to import service alerts from an EFA backend. It supports service alerts only; it does not import trip updates or vehicle positions.

## Configuration

- **Endpoint URL**: The EFA endpoint that provides JSON results for the `XML_ADDINFO_REQUEST` request.
- **Dialect**: `ADDINFO`, the dialect for retrieving service-alert information.

## Imported information

The data source reads the current information returned by the EFA endpoint. It uses each notice's affected routes and stops to determine which services the notice applies to:

- Line notices apply to their affected routes.
- Route notices apply to their affected routes and stops.
- Stop notices apply to their affected stops.

The notice priority determines its severity. Normal priority maps to informational, high priority maps to warning, and very high priority maps to severe. Other priorities use the unknown severity.

The notice title, description, and URL are taken from its information links. HTML markup and formatting in titles and descriptions are normalized for use as alert text. Validity ranges determine when the alert applies; an open-ended range has no end time.

For the detailed source-field mapping, see the [EFA-JSON service-alert transformer specification](../../../dev/transformers/efa_json_service_alerts_transformer.md).
