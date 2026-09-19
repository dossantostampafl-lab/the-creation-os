$ErrorActionPreference = "Continue"
Set-Location (Resolve-Path "$PSScriptRoot\..")

docker compose ps

$checks = @(
    @{ Name = "API"; Url = "http://127.0.0.1:8000/api/v1/health/ready" },
    @{ Name = "Frontend"; Url = "http://127.0.0.1:8080/healthz" },
    @{ Name = "Proxy"; Url = "http://127.0.0.1:8080/api/v1/health/ready" }
)

foreach ($check in $checks) {
    try {
        $response = Invoke-WebRequest -Uri $check.Url -UseBasicParsing -TimeoutSec 4
        Write-Host ("{0}: HEALTHY ({1})" -f $check.Name, $response.StatusCode)
    } catch {
        Write-Host ("{0}: UNHEALTHY" -f $check.Name)
    }
}

$lanIp = Get-NetIPConfiguration |
    Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.IPv4Address -ne $null } |
    Select-Object -First 1 -ExpandProperty IPv4Address |
    Select-Object -ExpandProperty IPAddress

Write-Host "Local UI: http://localhost:8080"
if ($lanIp) { Write-Host ("LAN UI:   http://{0}:8080" -f $lanIp) }
