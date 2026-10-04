# Clears the Range's disposable scenario state. The evidence journal and the snapshots are proof of what
# happened and are never removed here: "down -v" would delete every volume, so it is not used.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Compose = Join-Path $Root "compose.yml"
try { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:7070/reset" | Out-Null } catch { Write-Host "Controller unavailable; removing only the disposable state volumes directly." }
docker compose -f $Compose --profile cyber-range down --remove-orphans
# Only disposable scenario/campaign state goes. These volumes may not exist, which is fine.
docker volume rm creation-cyber-range_range_state 2>$null | Out-Null
docker volume rm creation-cyber-range_range_campaign_state 2>$null | Out-Null
Write-Host "Evidence and snapshots were preserved; scenario and campaign state were cleared."
