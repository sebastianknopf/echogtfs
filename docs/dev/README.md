# EchoGTFS Developer Documentation

This directory contains technical documentation for the EchoGTFS system, intended for developers and AI agents that need to understand, extend, or maintain the codebase.

## Contents

- [architecture.md](architecture.md): Overall system architecture, component responsibilities, data flow, and technology stack.
- [datasources.md](datasources.md): Data source purpose, transformer and processing architecture, base classes, execution modes, scheduling, and run coordination.
- [vdv453.md](vdv453.md): VDV453-VIS data source configuration, execution, and best-effort subscription parameters.
- [vdv454.md](vdv454.md): VDV454-AUS data source configuration, execution, and best-effort subscription parameters.
- [siricomservice.md](siricomservice.md): SIRI consumer integration, subscription lifecycle, health discovery, and network routing.
- [authentication.md](authentication.md): Authentication and authorization model, JWT lifecycle, sliding sessions, and role system.
- [realtime.md](realtime.md): Relations and implications bewteen realtime models in exports and internal handling.
- [realtime-storage.md](realtime-storage.md): MongoDB realtime collections, document structure, indices, write transactions, and snapshot reads for the exports.
- [gtfs-id-cache.md](gtfs-id-cache.md): Redis cache of nominal GTFS IDs, rebuild triggers, and bulk validation in the processing runs.
- [push-api.md](push-api.md): Push endpoint authentication, execution flow, scheduler integration, and error/status mapping.
- [internal-push-api.md](internal-push-api.md): Internal unauthenticated datasource execution endpoint and its network boundary.
- [differential-incremental.md](differential-incremental.md): End-to-end implementation of differential source sync and incremental trip-update merge/export semantics.
- [matching.md](matching.md): Matching-service behavior for resolving external realtime trip IDs to nominal GTFS trips, including cache flow and fallback stages.
- [stop-propagation.md](stop-propagation.md): Description of the stop propagation and stop event matching between delivered realtime stop events and nominal GTFS stop times.
- [transformation.md](transformation.md): Transformer output contract and internal datasource record model for service alerts, trip updates, and vehicle positions.
- [transformers/README.md](transformers/README.md): Index of implementation-oriented notes for the concrete transformers.
- [localization.md](localization.md): Frontend i18n system, translation key conventions, language loading, and adding new languages.
- [material-design.md](material-design.md): Custom Material Design 3 implementation in CSS and JavaScript, design tokens, component patterns, and UI conventions.
