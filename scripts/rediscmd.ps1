#Requires -Version 5.1
<#
.SYNOPSIS
Open an interactive Redis command session against the Timeline Redis container.

.DESCRIPTION
Reads Redis configuration from the .env file located in the repository root
and communicates with the running Redis container via docker exec.

When no argument is given the script starts an interactive rediscmd shell.

The custom command "CLEAR TRIPS" removes all Redis keys below the
"echogtfs:data:trips" cache area.

The custom command "LIST TRIPS" lists all Redis keys below the
"echogtfs:data:trips" cache area together with their values.

Other Redis commands are passed directly to redis-cli.

.EXAMPLE
# Interactive rediscmd session
.\scripts\rediscmd.ps1

.EXAMPLE
# Execute a single Redis command
.\scripts\rediscmd.ps1 "PING"

.EXAMPLE
# Clear all trip cache entries
.\scripts\rediscmd.ps1 "CLEAR TRIPS"

.EXAMPLE
# List all trip cache entries and their values
.\scripts\rediscmd.ps1 "LIST TRIPS"
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Resolve the repository root relative to this script's location.

$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile  = Join-Path $RepoRoot ".env"

if (-not (Test-Path $EnvFile)) {
    Write-Error ".env file not found at '$EnvFile'. Copy .env.example to .env and fill in your values."
}

# Parse key=value pairs from .env; ignore blank lines and comments.

$EnvVars = @{}
foreach ($Line in Get-Content $EnvFile) {
    $Line = $Line.Trim()

    if ($Line -eq "" -or $Line.StartsWith("#")) {
        continue
    }

    $Index = $Line.IndexOf("=")

    if ($Index -lt 1) {
        continue
    }

    $Key   = $Line.Substring(0, $Index).Trim()
    $Value = $Line.Substring($Index + 1).Trim()

    $EnvVars[$Key] = $Value
}

# Redis configuration.
#
# Values from .env override the defaults.

$RedisHost = "localhost"
$RedisPort = "6379"
$RedisPass = ""

if ($EnvVars.ContainsKey("REDIS_HOST") -and $EnvVars["REDIS_HOST"]) {
    $RedisHost = $EnvVars["REDIS_HOST"]
}

if ($EnvVars.ContainsKey("REDIS_PORT") -and $EnvVars["REDIS_PORT"]) {
    $RedisPort = $EnvVars["REDIS_PORT"]
}

if ($EnvVars.ContainsKey("REDIS_PASSWORD")) {
    $RedisPass = $EnvVars["REDIS_PASSWORD"]
}

$ContainerName = "echogtfs-redis-1"

# Verify the container is running before attempting to connect.

$Status = docker inspect --format "{{.State.Running}}" $ContainerName 2>$null

if ($Status -ne "true") {
    Write-Error "Container '$ContainerName' is not running. Start it with: docker compose up -d redis"
}

# Build redis-cli arguments.

$RedisArgs = @(
    "-h", $RedisHost,
    "-p", $RedisPort
)

if ($RedisPass) {
    $RedisArgs += @("-a", $RedisPass)
}

# Execute a Redis command through the Redis container.

function Invoke-RedisCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    docker exec -i $ContainerName redis-cli @RedisArgs @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "Redis command failed."
    }
}

# Clear all keys below the trip cache area.
#
# SCAN is used instead of KEYS so Redis is not blocked while traversing
# the key space.

function Clear-Trips {
    $Pattern = "echogtfs:data:trips:*"
    $Cursor  = "0"
    $Deleted = 0

    do {
        $ScanOutput = @(
            docker exec -i $ContainerName redis-cli @RedisArgs `
                SCAN $Cursor MATCH $Pattern COUNT 500
        )

        if ($LASTEXITCODE -ne 0) {
            throw "Redis SCAN failed."
        }

        if ($ScanOutput.Count -lt 1) {
            throw "Redis SCAN failed."
        }

        $Cursor = $ScanOutput[0].Trim()

        $Keys = @(
            $ScanOutput |
                Select-Object -Skip 1 |
                Where-Object {
                    $_ -and $_.Trim() -ne ""
                } |
                ForEach-Object {
                    $_.Trim()
                }
        )

        if ($Keys.Count -gt 0) {
            docker exec -i $ContainerName redis-cli @RedisArgs DEL @Keys | Out-Null

            if ($LASTEXITCODE -ne 0) {
                throw "Redis DEL failed."
            }

            $Deleted += $Keys.Count
        }

    } while ($Cursor -ne "0")

    Write-Host "$Deleted deleted"
}

# List all trip cache entries including their values.
#
# Output format:
# echogtfs:data:trips:some-key > some-value
#
# SCAN is used instead of KEYS so Redis is not blocked while traversing
# the key space.

function List-Trips {
    $Pattern = "echogtfs:data:trips:*"
    $Cursor  = "0"

    do {
        $ScanOutput = @(
            docker exec -i $ContainerName redis-cli @RedisArgs `
                SCAN $Cursor MATCH $Pattern COUNT 500
        )

        if ($LASTEXITCODE -ne 0) {
            throw "Redis SCAN failed."
        }

        if ($ScanOutput.Count -lt 1) {
            throw "Redis SCAN failed."
        }

        $Cursor = $ScanOutput[0].Trim()

        $Keys = @(
            $ScanOutput |
                Select-Object -Skip 1 |
                Where-Object {
                    $_ -and $_.Trim() -ne ""
                } |
                ForEach-Object {
                    $_.Trim()
                }
        )

        foreach ($Key in $Keys) {
            $Value = @(
                docker exec -i $ContainerName redis-cli @RedisArgs GET $Key
            )

            if ($LASTEXITCODE -ne 0) {
                throw "Redis GET failed for key '$Key'."
            }

            $ValueText = ($Value -join "`n").TrimEnd()

            Write-Host "$Key > $ValueText"
        }

    } while ($Cursor -ne "0")
}

# Execute a single command.

function Invoke-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InputCommand
    )

    $TrimmedCommand = $InputCommand.Trim()

    if (-not $TrimmedCommand) {
        return $true
    }

    $NormalizedCommand = $TrimmedCommand.ToUpperInvariant()

    switch ($NormalizedCommand) {
        "CLEAR TRIPS" {
            Clear-Trips
            break
        }

        "LIST TRIPS" {
            List-Trips
            break
        }

        "EXIT" {
            return $false
        }

        "QUIT" {
            return $false
        }

        default {
            $Arguments = $TrimmedCommand -split '\s+'
            Invoke-RedisCommand -Arguments $Arguments
            break
        }
    }

    return $true
}

if ($Command) {
    # Non-interactive: execute a single Redis command and exit.

    Invoke-Command -InputCommand $Command | Out-Host
}
else {
    # Interactive rediscmd shell.

    Write-Host "Redis command shell (type 'EXIT' or 'QUIT' to exit)"
    Write-Host ""
    Write-Host "CLEAR TRIPS - Remove all trip cache entries"
    Write-Host "LIST TRIPS - List all trip cache entries and their values"
    Write-Host "EXIT - Exit the shell"
    Write-Host "QUIT - Exit the shell"
    Write-Host ""

    while ($true) {
        try {
            $InputCommand = Read-Host "echogtfs="

            if ($null -eq $InputCommand) {
                break
            }

            $Result = Invoke-Command -InputCommand $InputCommand

            if ($Result -eq $false) {
                break
            }
        }
        catch {
            Write-Host $_.Exception.Message
        }
    }
}