# Internal Push API

`POST /internal/execute/datasource/{source_id}` synchronously passes a request body to a data source adapter and returns the resulting synchronization counts. The endpoint is registered without the `/api` prefix by `internal_execute.py`.

The endpoint has no authentication. It is intended for trusted internal callers, currently the SIRI consumer service subscription sink. The route is not exposed through the frontend NGINX server: NGINX returns `404` for `/internal` and `/internal/...`, and Docker Compose exposes the backend port only to the Compose network. Do not publish or externally proxy the backend port.

## Request and Response

- Method: `POST`
- Path: `/internal/execute/datasource/{source_id}`
- Body: the raw payload received by the caller
- Content type: forwarded from the request's `Content-Type` header
- Success: `200` with `added`, `updated`, and `deleted` counters

The handler reads the request body and awaits `DatasourceSchedulerService.run_internal_push_task(...)` before returning. The shared push execution path checks that the source exists and is active, that the scheduler is not closing, that a GTFS import is not in progress, and that the source is not already running. It deliberately does not require `event_based` execution. This is how a subscription-based source receives SIRI payloads; the public push endpoint remains restricted to event-based sources.

Scheduler and adapter errors are mapped to their corresponding HTTP status and detail response. See [push-api.md](push-api.md) for shared payload processing and logging behavior.

## Subscription Sink

`SiriSubscriptionService` configures the SIRI consumer subscription with this endpoint as its HTTP sink. The `source_id` is also the subscription reference, and the sink sets `max_concurrency` to `1`. The service constructs this internal configuration itself, so a datasource's SIRI parameters cannot override the callback reference or sink.

The complete subscription lifecycle and network boundaries are described in [siricomservice.md](siricomservice.md).
