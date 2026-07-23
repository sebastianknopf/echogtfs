# Realtime Relations & Implications

The realtime data model is complex regarding the internal relations and information implied between the realtime models.

Seen from GTFS-RT perspective, we have three _toplevel realtime entities_: `ServiceAlerts`, `TripUpdates` and `VehiclePostions`. This document provides an overview over the _toplevel realtime entities_ and the _internal modelling_ of the realtime objects.

This chapter describes the references between the internal realtime models and their implications regarding the validitiy flag.

## ServiceAlerts

The service alerts to not have implications or relations to other toplevel entities. Internally, the service alerts consist of:

- a table for alert definition (entrypoint for `GtfsRealtimeServiceAlertsExportService`)
- a table for validity periods related to the alerts
- a table for informed entities related to the alerts
- a table for translations related to the alerts

### Validity Flag

- a service alert is considered as valid, when all informed entities are valid
- an informed entity is considered as valid, when the informed entity type matches an existing nominal GTFS-ID of the defined entity

### Implications

The `GtfsRealtimeServiceAlertsExportService` exports all service alerts which are set to active, regardless whether the service alert is valid or not.

## TripUpdates

The trip updates may have implications on the vehicle positions. Internally, the trip updates consist of:

- a table for realtime trips (entrypoint for `GtfsRealtimeTripUpdatesExportService`)
- a table for stop events related to the trip

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

- a table for actual vehicle position information (entrypoint for `GtfsRealtimeVehiclePositionsExportService`)

### Relations

- a vehicle position **must not live without a trip** object

### Validity Flag

- a vehicle is considered as valid, when the referenced referenced trip is valid; see trip validity for reference

### Implications

The `GtfsRealtimeVehiclePositionsExportService` exports all vehicles as vehicle position which are set to active, regardless whether the vehicle is valid or not.


