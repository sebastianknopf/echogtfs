#!/usr/bin/env bash
# volumeinfo — Lists all Docker Compose volumes with their size and mountpoint.
#
# Usage:
#   ./scripts/volumeinfo.sh
#
# Prints one line per Docker volume in the current Docker Compose project:
#   <volume>    <size in GB>    <mountpoint>

set -euo pipefail

# Resolve the repository root relative to this script's location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

(
    cd "$REPO_ROOT"

    docker compose volumes -q | while read -r volume; do
        mountpoint=$(docker volume inspect -f '{{ .Mountpoint }}' "$volume")
        size_bytes=$(du -sb "$mountpoint" | cut -f1)
        size_gb=$(awk -v bytes="$size_bytes" 'BEGIN { printf "%.1f GB", bytes/1024/1024/1024 }')

        if [ ${#volume} -ge 20 ]; then
            tabs=$'\t'
        else
            tabs=$'\t\t'
        fi

        printf "%s%s%s\t\t%s\n" "$volume" "$tabs" "$size_gb" "$mountpoint"
    done
)