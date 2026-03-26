# echogtfs

A lightweight CMS for creating and managing GTFS-RT ServiceAlerts based on existing GTFS feeds. The system allows transit agencies to create real-time service alerts and integrate additional data sources such as SIRI-SX.

## Overview

**echogtfs** is designed to simplify the creation and distribution of GTFS-Realtime ServiceAlerts. It provides:

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

## Prerequisites

- Docker and Docker Compose
- An existing GTFS feed (static)

## Installation

### Using Docker Compose (Recommended)

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd echogtfs
   ```

2. **Create environment configuration:**
   ```bash
   cp .env.example .env
   ```

3. **Edit the `.env` file and configure:**
   - `SECRET_KEY` – Generate a secure key (e.g., `openssl rand -hex 32`)
   - `POSTGRES_PASSWORD` – Set a strong database password (required)
   - `FIRST_SUPERUSER_PASSWORD` – Admin password for initial login (required)
   - `FRONTEND_PORT` – Port for web interface (default: 80)
   
   **Important:** All password fields are required and have no defaults for security reasons.

4. **Start the application:**
   ```bash
   docker-compose up -d
   ```

5. **Access the web interface:**
   - Open your browser at http://localhost (or the configured port)

## Configuration

### Environment Variables

Key settings in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | JWT secret key (required) | none |
| `POSTGRES_PASSWORD` | Database password (required) | none |
| `FIRST_SUPERUSER` | Initial admin username | `admin` |
| `FIRST_SUPERUSER_PASSWORD` | Initial admin password (required) | none |
| `DOCS_ENABLED` | Enable API documentation | `false` |
| `FRONTEND_PORT` | Web interface port | `80` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token lifetime | `30` |

### GTFS Feed Configuration

After logging in, configure your GTFS data source via the settings interface:

1. Navigate to **Settings**
2. Add your GTFS feed URL or upload a GTFS file
3. The system will import the static GTFS data
4. You can now create ServiceAlerts referencing routes, stops, and trips from your GTFS feed

## Usage

### Managing ServiceAlerts

1. **Log in** with your admin credentials
2. Navigate to **Alerts**
3. **Create a new alert:**
   - Select affected routes, stops, or trips from your GTFS feed
   - Set alert severity and effect
   - Add descriptions in multiple languages if needed
   - Define active periods
4. **Publish** the alert to make it available via the GTFS-RT feed

### Accessing GTFS-RT Feeds

ServiceAlerts are available via GTFS-Realtime protocol:

```
GET /api/realtime/service-alerts.pbf
```

The endpoint returns protocol buffer formatted GTFS-RT data that can be consumed by trip planners and real-time transit applications. By adding `?json` as query parameter, the output will be in JSON.

You also can configure a different endpoint name in the backend if required.

### Integrating Additional Data Sources

The system supports integration of additional alert sources such as SIRI-SX. Configure external sources in the settings interface to automatically import and convert alerts to GTFS-RT format.

## Development

### Local Setup

1. **Install Python dependencies:**
   ```bash
   cd backend
   pip install -e .
   ```

2. **Set up PostgreSQL database**

3. **Configure environment variables** for local development

4. **Run the backend:**
   ```bash
   python -m echogtfs
   ```

## Updating

To update to the latest version:

```bash
git pull
docker-compose down
docker-compose build
docker-compose up -d
```

## Troubleshooting

**Database connection issues:**
```bash
docker-compose logs database
```

**Backend service issues:**
```bash
docker-compose logs backend
```

**Reset and restart:**
```bash
docker-compose down -v
docker-compose up -d
```

## License

This project is licensed under the Apache 2.0 license. See [LICENSE.md](LICENSE.md) for the full license text.
