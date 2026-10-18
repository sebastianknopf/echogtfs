# SIRI Communication Service Architecture

`siricomservice` is the optional SIRI consumer component used to manage long-running SIRI subscriptions. EchoGTFS owns datasource configuration and realtime processing; the consumer owns SIRI subscription communication and delivers received payloads back to EchoGTFS.

## Components and Boundaries

- `SiriSubscriptionService` is the backend HTTP client for the consumer. It implements `SiriSubscriptionServiceInterface` and is registered as an application-wide service during startup.
- `sources.py` coordinates subscription lifecycle with datasource creation, update, activation, deactivation, and deletion.
- The SIRI datasources inheriting from `SubscriptionDatasourceBase` provide their subscription parameters through `get_subscription_params()`.
- `internal_execute.py` receives sink callbacks and delegates synchronous processing to the datasource scheduler. See [internal-push-api.md](internal-push-api.md) for its request contract and security boundary.

The service uses `http://siricomservice:8080` on the Compose network. Its management API is under `/api`; liveness and readiness checks are under `/health`.

## Subscription Lifecycle

1. A subscription-based datasource is persisted with its configuration and datasource ID.
2. If the datasource is active, `sources.py` builds the SIRI datasource instance and obtains its subscription parameters.
3. `SiriSubscriptionService` merges those parameters with its enforced internal settings:
   - `subscription_ref` is the datasource ID converted to a string.
   - `delivery_mode` is `direct`.
   - The HTTP sink targets `http://backend:8000/internal/execute/datasource/{source_id}` with `max_concurrency: 1`.
4. The service creates the subscription. Incoming payloads are delivered to the internal push endpoint, then processed synchronously through the normal datasource pipeline.
5. Deactivation and deletion stop the subscription before continuing with their remaining datasource operations. Updates stop the previous subscription before persisting the update, then start a subscription with the updated configuration if the source remains active.

Datasource-specific parameters include the provider URL, participant reference, optional consumer address, service type, and SIRI subscription timing and heartbeat settings. The datasource implementations set `logging` to `false`. The service's enforced sink settings take precedence over any overlapping datasource parameters.

Create, stop, status, and restart operations are awaited. The service treats the consumer API's expected success statuses as success (`201` for create, `204` for delete, and `200` for status/restart); a non-success status or an HTTP error is reported as failure. Subscription start, stop, and restart requests have no client timeout. Health and subscription-status requests use a 15-second timeout.
## Discovery and Health

The backend exposes two authenticated checks through `SiriSubscriptionService`:

- `/api/capabilities` includes `siricomservice` only when `/health/ready` returns HTTP `200`. The frontend uses this capability to show subscription-related UI.
- `/api/service/siri/health` returns whether `/health/live` returns HTTP `200`. The dashboard uses it for service health status.

Transport errors and non-`200` responses produce `false`. These checks distinguish readiness for capability discovery from process liveness for health display.

## Deployment and External Routing

Compose assigns `siricomservice` to the `siripubsub` profile. Start the optional component with:

```text
docker compose --profile siripubsub up -d
```

Without that profile, Compose does not start the service. The backend can still start; capability discovery then omits `siricomservice`.

The frontend NGINX server on port `8080` proxies SIRI communication paths to the consumer, resolving its hostname lazily so NGINX can start when the profile is disabled. It always returns `404` for `/api` and `/api/...` on that listener. The `/status` page is also blocked unless `SIRI_STATUS_ENABLED=true`. Other paths continue to proxy to the consumer.

The consumer management API is therefore reachable to the backend over the private Compose network, but not through the frontend's SIRI listener. The subscription callback is likewise internal and unauthenticated; its safety depends on keeping the backend port and `/internal/...` route inaccessible to untrusted clients.
