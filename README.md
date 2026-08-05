[![Tests](https://github.com/sebastianknopf/echogtfs/actions/workflows/tests.yml/badge.svg)](https://github.com/sebastianknopf/echogtfs/actions/workflows/tests.yml)

# echogtfs

A lightweight data integration platform for creating and aggregating GTFS-RT complicant based on existing GTFS feeds. The system allows transit agencies to create real-time data in GTFS-RT format.

See the user manual here: [sebastianknopf.github.io/echogtfs](sebastianknopf.github.io/echogtfs)

It provides:

- A web-based interface for managing service alerts
- Integration with existing static GTFS feeds
- Support for additional data sources (SIRI-SX and others)
- GTFS-RT feed generation

## Technology Stack

**Backend:**
- FastAPI (Python 3.11+)
- PostgreSQL with async support
- SQLAlchemy ORM
- Pydantic for validation

**Frontend:**
- HTML/CSS/JavaScript
- NGINX web server

## Requirements

- Docker and Docker Compose
- An existing GTFS static feed
- At least 8GB RAM

## Development

See [developer docs here](docs/dev/README.md).

## License

This project is licensed under the Apache 2.0 license. See [LICENSE.md](LICENSE.md) for the full license text.
