$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Compose = Join-Path $Root "compose.yml"
docker compose -f $Compose --profile cyber-range up -d --build
& (Join-Path $Root "scripts\verify.ps1")
