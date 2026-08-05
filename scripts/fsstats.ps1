#!/usr/bin/env pwsh
# volumeinfo — Lists all Docker Compose volumes with their size and mountpoint.
#
# Usage:
#   ./scripts/volumeinfo.ps1
#
# Prints one line per Docker volume in the current Docker Compose project:
#   <volume>    <size in GB>    <mountpoint>

$ErrorActionPreference = "Stop"

# Resolve the repository root relative to this script's location.
$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Split-Path -Parent $ScriptDir

Push-Location $RepoRoot

try {
    # Determine the Compose project name.
    $ProjectName = docker compose config --format json |
        ConvertFrom-Json |
        Select-Object -ExpandProperty name

    if ([string]::IsNullOrWhiteSpace($ProjectName)) {
        throw "Could not determine Docker Compose project name."
    }

    # Get actual Docker volumes belonging to this Compose project.
    $Volumes = docker volume ls `
        --filter "label=com.docker.compose.project=$ProjectName" `
        --format "{{.Name}}"

    foreach ($volume in $Volumes) {
        $mountpoint = docker volume inspect -f '{{ .Mountpoint }}' $volume

        $sizeBytes = docker run --rm `
            -v "${volume}:/data:ro" `
            alpine sh -c "du -sb /data | cut -f1"

        $sizeGb = "{0:N1} GB" -f ([double]$sizeBytes / 1GB)

        if ($volume.Length -ge 20) {
            $tabs = "`t"
        }
        else {
            $tabs = "`t`t"
        }

        Write-Output "$volume$tabs$sizeGb`t`t$mountpoint"
    }
}

finally {
    Pop-Location
}