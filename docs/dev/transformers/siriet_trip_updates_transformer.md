# SiriEtTripUpdatesTransformer

## Purpose

This transformer converts SIRI-ET XML into EchoGTFS's internal trip-update structure.

## Extraction Rules

- The transformer scans the XML for `EstimatedVehicleJourney` elements and processes each journey individually.
- Each journey is first checked for `Monitored`. Unmonitored journeys are discarded.
- If an operator filter is configured, the journey is processed only when `OperatorRef` is contained in the allowed list.
- For journeys with `ExtraJourney=true`, the transformer also checks whether `IsCompleteStopSequence=true` is set. Otherwise the journey is discarded and a warning is logged.
- `route_id` and `trip_id` are derived from `LineRef` and `FramedVehicleJourneyRef/DatedVehicleJourneyRef`.
- The start time is derived from `EstimatedCalls` or `RecordedCalls` and the first call times.
- Stop events are built from `RecordedCall` and `EstimatedCall` entries. Each stop receives a stop ID, order, arrival and departure times, and a schedule relationship.
- For a `RecordedCall`, the schedule relationship is set to `SKIPPED` when `Cancellation=true`; otherwise it is set to `NO_DATA` when no real-time data is present.
- For an `EstimatedCall`, the schedule relationship is set to `SKIPPED` when `Cancellation=true`, to `ADDED` when `ExtraCall=true`, and otherwise to `NO_DATA` when no expected times are present.
- The trip relationship is set to `SCHEDULED`, `NEW`, or `CANCELED` based on `Cancellation` and `ExtraJourney` state.
- A journey is processed only if it falls within a time window that is not too far in the future and reaches at least the present time.

- Currently, only journeys with `IsCompleteStopSequence=true` are processed. All other journeys are discarded.
