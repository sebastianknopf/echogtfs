#Requires -Version 5.1
<#
.SYNOPSIS
    Starts the backend in Docker Compose debug mode.

.DESCRIPTION
    Starts the Docker Compose setup using both docker-compose.yml and
    docker-compose.debug.yml.

    By default the containers are rebuilt before being started.

    When -NoBuild is specified the existing images are reused and only the
    containers are restarted.

.PARAMETER NoBuild
    Skip the image build step and only restart the Docker Compose setup.

.EXAMPLE
    .\scripts\excdebug.ps1

.EXAMPLE
    .\scripts\excdebug.ps1 -NoBuild
#>

[CmdletBinding()]
param(
    [switch]$NoBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Resolve the repository root relative to this script's location.
$RepoRoot = Split-Path -Parent $PSScriptRoot

$ComposeFiles = @(
    "-f", (Join-Path $RepoRoot "docker-compose.yml"),
    "-f", (Join-Path $RepoRoot "docker-compose.debug.yml")
)

Write-Host ""
Write-Host "Starting Docker Compose debug environment..." -ForegroundColor Cyan

if ($NoBuild) {
    docker compose @ComposeFiles up -d
}
else {
    docker compose @ComposeFiles up -d --build
}

if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker Compose startup failed."
}

Write-Host ""
Write-Host "Docker Compose debug environment started successfully." -ForegroundColor Green