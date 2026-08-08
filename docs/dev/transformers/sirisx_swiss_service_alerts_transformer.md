# SiriSxSwissServiceAlertsTransformer

## Purpose

This transformer processes the Swiss profile of SIRI-SX and extracts the same internal alert data as the standard SIRI-SX transformer, using Swiss-specific value mappings.

## Extraction Rules

- All `PtSituationElement` entries in the XML are scanned.
- A situation is processed only if it matches the configured participant filter.
- A publication is considered only if the situation falls within a valid publication window.
- The situation is identified by `SituationNumber` and is assigned an internal ID.
- Validity and publication periods are extracted from `ValidityPeriod` and `PublicationWindow`.
- Translations are built from `SummaryContent`, `ReasonContent`, `DescriptionContent`, `ConsequenceContent`, `RecommendationContent`, or `RemarkContent`.
- Language variants are taken from the XML language attribute.
- Internal values for `AlertCause` and `Severity` are assigned through Swiss-specific mappings.
- Affected networks, lines, stops, and vehicle journeys are extracted from `Affects`.
- Trip IDs are taken from `VehicleJourneyRef` or `DatedVehicleJourneyRef` for vehicle journeys.
- If no meaningful text is found, the situation is discarded.
