#!/usr/bin/env bash

set -euo pipefail

# Resolve the repository root relative to this script's location.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo ".env file not found at '$ENV_FILE'. Copy .env.example to .env and fill in your values." >&2
    exit 1
fi

# Parse key=value pairs from .env; ignore blank lines and comments.

declare -A ENV_VARS

while IFS= read -r LINE || [[ -n "$LINE" ]]; do
    LINE="${LINE#"${LINE%%[![:space:]]*}"}"
    LINE="${LINE%"${LINE##*[![:space:]]}"}"

    [[ -z "$LINE" ]] && continue
    [[ "$LINE" == \#* ]] && continue

    if [[ "$LINE" != *=* ]]; then
        continue
    fi

    KEY="${LINE%%=*}"
    VALUE="${LINE#*=}"

    KEY="${KEY%"${KEY##*[![:space:]]}"}"
    VALUE="${VALUE#"${VALUE%%[![:space:]]*}"}"
    VALUE="${VALUE%"${VALUE##*[![:space:]]}"}"

    ENV_VARS["$KEY"]="$VALUE"
done < "$ENV_FILE"

# Redis configuration.
#
# Values from .env override the defaults.

REDIS_HOST="${ENV_VARS[REDIS_HOST]:-localhost}"
REDIS_PORT="${ENV_VARS[REDIS_PORT]:-6379}"
REDIS_PASS="${ENV_VARS[REDIS_PASSWORD]:-}"

CONTAINER_NAME="echogtfs-redis-1"

# Verify the container is running before attempting to connect.

STATUS="$(docker inspect --format '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || true)"

if [[ "$STATUS" != "true" ]]; then
    echo "Container '$CONTAINER_NAME' is not running. Start it with: docker compose up -d redis" >&2
    exit 1
fi

# Build redis-cli arguments.

REDIS_ARGS=(
    -h "$REDIS_HOST"
    -p "$REDIS_PORT"
)

if [[ -n "$REDIS_PASS" ]]; then
    REDIS_ARGS+=(-a "$REDIS_PASS")
fi

# Execute a Redis command through the Redis container.

invoke_redis_command() {
    docker exec -i "$CONTAINER_NAME" redis-cli \
        "${REDIS_ARGS[@]}" \
        "$@"
}

# Clear all keys below the trip cache area.
#
# SCAN is used instead of KEYS so Redis is not blocked while traversing
# the key space.

clear_trips() {
    local pattern="echogtfs:data:trips:*"
    local cursor="0"
    local deleted=0

    while true; do
        local scan_output

        scan_output="$(
            docker exec -i "$CONTAINER_NAME" redis-cli \
                "${REDIS_ARGS[@]}" \
                SCAN "$cursor" MATCH "$pattern" COUNT 500
        )"

        # The first line is the cursor.
        cursor="$(printf '%s\n' "$scan_output" | head -n 1)"

        if [[ -z "$cursor" ]]; then
            echo "Redis SCAN failed." >&2
            return 1
        fi

        # Everything after the first line is a key.
        mapfile -t keys < <(
            printf '%s\n' "$scan_output" |
                tail -n +2 |
                sed '/^[[:space:]]*$/d'
        )

        if [[ ${#keys[@]} -gt 0 ]]; then
            docker exec -i "$CONTAINER_NAME" redis-cli \
                "${REDIS_ARGS[@]}" \
                DEL "${keys[@]}" >/dev/null

            ((deleted += ${#keys[@]}))
        fi

        [[ "$cursor" == "0" ]] && break
    done

    echo "$deleted deleted"
}

# List all trip cache entries including their values.
#
# Output format:
# echogtfs:data:trips:some-key > some-value
#
# SCAN is used instead of KEYS so Redis is not blocked while traversing
# the key space.

list_trips() {
    local pattern="echogtfs:data:trips:*"
    local cursor="0"

    while true; do
        local scan_output

        scan_output="$(
            docker exec -i "$CONTAINER_NAME" redis-cli \
                "${REDIS_ARGS[@]}" \
                SCAN "$cursor" MATCH "$pattern" COUNT 500
        )"

        # The first line is the cursor.
        cursor="$(printf '%s\n' "$scan_output" | head -n 1)"

        if [[ -z "$cursor" ]]; then
            echo "Redis SCAN failed." >&2
            return 1
        fi

        # Everything after the first line is a key.
        mapfile -t keys < <(
            printf '%s\n' "$scan_output" |
                tail -n +2 |
                sed '/^[[:space:]]*$/d'
        )

        for key in "${keys[@]}"; do
            local value

            value="$(
                docker exec -i "$CONTAINER_NAME" redis-cli \
                    "${REDIS_ARGS[@]}" \
                    GET "$key"
            )"

            printf '%s > %s\n' "$key" "$value"
        done

        [[ "$cursor" == "0" ]] && break
    done
}

# Execute a single command.

invoke_command() {
    local input_command="$1"

    # Trim leading and trailing whitespace.

    input_command="${input_command#"${input_command%%[![:space:]]*}"}"
    input_command="${input_command%"${input_command##*[![:space:]]}"}"

    [[ -z "$input_command" ]] && return 0

    # Normalize the command for custom command matching.

    local normalized_command
    normalized_command="$(printf '%s' "$input_command" | tr '[:lower:]' '[:upper:]')"

    case "$normalized_command" in
        "CLEAR TRIPS")
            clear_trips
            ;;

        "LIST TRIPS")
            list_trips
            ;;

        "EXIT"|"QUIT")
            return 2
            ;;

        *)
            # Split the command into arguments and pass them to redis-cli.

            read -r -a arguments <<< "$input_command"

            invoke_redis_command "${arguments[@]}"
            ;;
    esac

    return 0
}

# Non-interactive: execute a single Redis command and exit.

if [[ -n "${1:-}" ]]; then
    invoke_command "$1"
    exit $?
fi

# Interactive rediscmd shell.

echo "CLEAR TRIPS - Remove all trip cache entries"
echo "LIST TRIPS - List all trip cache entries and their values"
echo "EXIT - Exit the shell"
echo "QUIT - Exit the shell"
echo

while true; do
    printf "echogtfs=# "

    if ! IFS= read -r input_command; then
        echo
        break
    fi

    if invoke_command "$input_command"; then
        :
    else
        exit_code=$?

        if [[ "$exit_code" -eq 2 ]]; then
            break
        fi

        echo "Command failed." >&2
    fi
done