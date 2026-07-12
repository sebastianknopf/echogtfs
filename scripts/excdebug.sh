#!/usr/bin/env bash
# dbcmd — Starts the backend in Docker Compose debug mode.
#
# Usage:
#   ./scripts/excdebug.sh
#   ./scripts/excdebug.sh --nobuild
#   ./scripts/excdebug.sh -n
#
# By default the containers are rebuilt before being started.

set -euo pipefail

NO_BUILD=false

case "${1:-}" in
    --nobuild|-n)
        NO_BUILD=true
        ;;
    "")
        ;;
    *)
        echo "Usage: $0 [--nobuild|-n]"
        exit 1
        ;;
esac

# Resolve the repository root relative to this script's location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

COMPOSE_FILES=(
    -f "$REPO_ROOT/docker-compose.yml"
    -f "$REPO_ROOT/docker-compose.debug.yml"
)

echo
echo "Starting Docker Compose debug environment..."

if $NO_BUILD; then
    docker compose "${COMPOSE_FILES[@]}" up -d
else
    docker compose "${COMPOSE_FILES[@]}" up -d --build
fi

echo
echo "Docker Compose debug environment started successfully."