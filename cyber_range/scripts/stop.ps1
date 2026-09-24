$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
docker compose -f (Join-Path $Root "compose.yml") --profile cyber-range down --remove-orphans
