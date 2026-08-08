# SiriSxServiceAlertsTransformer

## Purpose

This transformer extracts the alert data required by EchoGTFS from SIRI-SX messages and builds the internal service-alert structure.

## Extraction Rules

- All `PtSituationElement` entries in the SIRI-SX XML are scanned.
- A situation is processed only if it matches the configured participant filter.
- A publication is considered only if the situation falls within a valid publication window.
- The situation is identified by `SituationNumber` and is assigned an internal ID.
- Validity and publication periods are extracted from `ValidityPeriod` and `PublicationWindow`.
- Translation content is derived from `Summary`, `Detail`, `Description`, or a `TextualContent` block.
- HTML tags are removed from the text, and special characters are normalized.
- The language is taken from the XML language attribute or a fallback language value.
- Information about affected networks, lines, stops, and vehicle journeys is extracted from `PublishingAction` and `Affects` structures.
- Trip references are created from `VehicleJourneyRef` or `DatedVehicleJourneyRef` values.
- If no usable text content is found, the situation is discarded.
