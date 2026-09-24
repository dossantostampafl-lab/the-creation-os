$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Compose = Join-Path $Root "compose.yml"
try { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:7070/reset" | Out-Null } catch { Write-Host "Controller unavailable; resetting disposable Docker state." }
docker compose -f $Compose --profile cyber-range down -v --remove-orphans
