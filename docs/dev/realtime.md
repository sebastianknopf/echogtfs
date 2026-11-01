# Realtime Relations & Implications

The realtime data model is complex regarding the internal relations and information implied between the realtime models.

Seen from GTFS-RT perspective, we have three _toplevel realtime entities_: `ServiceAlerts`, `TripUpdates` and `VehiclePostions`. This document provides an overview over the _toplevel realtime entities_ and the _internal modelling_ of the realtime objects.

This chapter describes the references between the internal realtime models and their implications regarding the validitiy flag.

## Processing Architecture

Realtime synchronization is separated from datasource-specific I/O. `DatasourceBase` forwards transformed payloads to `RealtimeProcessingDispatcherService`, which dispatches by top-level entity type to `ServiceAlertProcessingService`, `TripUpdateProcessingService`, or `VehiclePositionProcessingService`. Shared validation and processing helpers are provided by `RealtimeProcessingServiceBase`.

`TripUpdateProcessingService` uses the existing `MatchingService` exclusively for realtime-trip to nominal-trip matching. Stop-event occurrence matching, complete-sequence reconciliation, incremental merging, and delay propagation are handled separately by `StopEventPropagationService`.

## ServiceAlerts

The service alerts to not have implications or relations to other toplevel entities. Internally, the service alerts consist of:

- a service alert document in `realtime_service_alerts` (entrypoint for `GtfsRealtimeServiceAlertsExportService`) with embedded:
  - validity periods
  - informed entities
  - translations

### Validity Flag

- a service alert is considered as valid, when all informed entities are valid
- an informed entity is considered as valid, when the informed entity type matches an existing nominal GTFS-ID of the defined entity

### Implications

The `GtfsRealtimeServiceAlertsExportService` exports all service alerts which are set to active, regardless whether the service alert is valid or not.

## TripUpdates

The trip updates may have implications on the vehicle positions. Internally, the trip updates consist of:

- a trip update document in `realtime_trip_updates` (entrypoint for `GtfsRealtimeTripUpdatesExportService`) with embedded stop events

The trip update documents carry no vehicle data. The trip update export attaches the vehicle position of the same matched `trip_id` from `realtime_vehicle_positions` within the same snapshot.

Detailed behavior for partial stop sequences, incremental merge propagation, and export rules is documented in [differential-incremental.md](differential-incremental.md).

### Relations

- a realtime trip **may live without stop events**, when it has schedule relationship `DELETED` or `CANCELED` or only the vehicle information is available
- a realtime trip **may live without a vehicle** object

### Validity Flag

- a trip is considered as valid, when the trip ID matches an existing nominal GTFS-ID and all existing stop events are considered as valid
- a stop event is considered as valid, when the stop ID matches an existing nominal GTFS-ID

### Implications

The `GtfsRealtimeTripUpdatesExportService` exports all trips as trip update which are set to active, regardless whether the trip is valid or not.

If a trip contains no stop events, the trip is not exported at all, **besides the schedule relationship is set to `DELETED` or `CANCELED`**.

## VehiclePositions

The vehicle positions may have implications on the vehicle position. Internall, the vehicle positions consist of:

- a vehicle position document in `realtime_vehicle_positions` (entrypoint for `GtfsRealtimeVehiclePositionsExportService`) with an embedded trip descriptor

A vehicle position has no assignment type of its own, it belongs to the embedded trip descriptor. Besides the trip validity flags, the vehicle position carries a nullable `stop_id` (current stop) and the flag `is_stop_valid` (default `true`), which is set during processing and is not part of the transformer output.

### Relations

- a vehicle position **must not live without a trip** object

The storage layout, indices, and snapshot behavior of the three collections are documented in [realtime-storage.md](realtime-storage.md).

### Validity Flag

- a vehicle position is considered as valid, when the embedded trip descriptor is valid (`is_trip_valid` and `is_route_valid`) and `is_stop_valid` is true
- the vehicle's own `is_stop_valid` flag is false when `stop_id` is set but not a nominal GTFS stop ID
- a new vehicle is created with `is_active = false` when `is_stop_valid`, `trip.is_trip_valid` or `trip.is_route_valid` is false

### Implications

The `GtfsRealtimeVehiclePositionsExportService` exports all vehicles as vehicle position which are set to active, regardless whether the vehicle is valid or not.


