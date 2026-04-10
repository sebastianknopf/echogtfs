# EchoGTFS - Copilot Instructions

## Project Overview

EchoGTFS is a lightweight CMS for creating and managing GTFS-Realtime ServiceAlerts based on existing GTFS feeds. The system consists of:

- **Backend**: Python/FastAPI service with PostgreSQL database
- **Frontend**: Vanilla JavaScript web interface with i18n support
- **Deployment**: Docker-based containerized application

## General Development Principles

### Code Changes
- **Minimize changes**: Only modify code that is directly relevant to the task
- **Targeted edits**: Make the smallest possible changes to achieve the goal
- **Refactoring**: Allowed when it meaningfully improves code quality, maintainability, or performance
- **Preserve behavior**: Existing functionality must not break unless explicitly requested

### Code Quality
- Write clean, readable, and idiomatic code
- Follow existing code patterns and conventions in the project
- Maintain consistent formatting with the existing codebase
- Add comments only when the code's intent is not self-evident

### Testing
- New features and modules should be covered by appropriate tests
- Bug fixes should include tests to prevent regression when applicable
- Follow project-specific testing guidelines (see backend/frontend instructions)

### Documentation
- Update relevant documentation when making functional changes
- Keep inline documentation concise and meaningful
- Document complex algorithms or non-obvious design decisions

### API Consistency
- **When modifying API endpoints** (either in backend or frontend):
  - Ensure changes are synchronized between backend implementation and frontend consumption
  - Update both sides to maintain API contract compatibility
  - Verify request/response schemas match on both ends
  - Test the complete request/response cycle after changes
- Backend API changes require corresponding frontend updates and vice versa
- Breaking API changes must be communicated and coordinated

## Project Structure

```
echogtfs/
├── backend/              # Python FastAPI backend
│   ├── src/echogtfs/    # Main application code
│   │   ├── routers/     # API endpoints
│   │   ├── services/    # Business logic & data import
│   │   │   └── adapters/ # External data source adapters
│   │   └── migrations/  # Database schema migrations
│   └── tests/           # Unit tests
├── frontend/            # Vanilla JavaScript frontend
│   ├── js/             # JavaScript modules
│   ├── css/            # Stylesheets
│   └── index.html      # Main HTML file
└── docs/               # Documentation
    └── manual/         # User manual
```

## Technology Constraints

### Backend
- Python >= 3.11 (minimum version)
- FastAPI, SQLAlchemy, PostgreSQL
- No new dependencies without explicit approval

### Frontend
- Vanilla JavaScript only (no frameworks like React, Vue, Angular)
- HTML5 and CSS3
- NGINX for serving static files
- No build tools or transpilation required

## Docker Environment

The application runs in Docker containers:
- `backend`: Python/FastAPI service
- `frontend`: NGINX web server
- `db`: PostgreSQL database

Configuration is managed via `.env` file based on `.env.example`.
