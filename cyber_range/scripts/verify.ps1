$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Compose = Join-Path $Root "compose.yml"
docker compose -f $Compose --profile cyber-range config --quiet
$Urls = @("http://127.0.0.1:7070/health","http://127.0.0.1:3000/","http://127.0.0.1:8080/WebGoat","http://127.0.0.1:9090/WebWolf")
foreach ($Url in $Urls) {
  $ok = $false
  for ($i=0; $i -lt 60; $i++) {
    try { $r=Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {$ok=$true;break} } catch {}
    Start-Sleep -Seconds 2
  }
  if (-not $ok) { throw "Cyber Range verification failed: $Url" }
}
Write-Host "Creation Cyber Range v1 verified on loopback-only endpoints."
