param(
    [switch]$PurgeData
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

if ($PurgeData) {
    Write-Warning "PurgeData removes the local PostgreSQL and Redis Docker volumes."
    docker compose down -v --remove-orphans
} else {
    docker compose down --remove-orphans
}

if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose stop failed."
}
