param(
    [switch]$Rebuild = $true
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found. Start Docker Desktop and ensure docker is available in PATH."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Engine is not available. Start Docker Desktop and retry."
}

$envCreated = $false
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $envCreated = $true
}

function Get-DotEnvValue([string]$Name) {
    $line = Get-Content ".env" | Where-Object { $_ -match ("^" + [regex]::Escape($Name) + "=") } | Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -split "=", 2)[1]
}

function Set-DotEnvValue([string]$Name, [string]$Value) {
    $content = Get-Content ".env" -Raw
    $pattern = "(?m)^" + [regex]::Escape($Name) + "=.*$"
    if ($content -match $pattern) {
        $content = [regex]::Replace($content, $pattern, "$Name=$Value")
    } else {
        if ($content.Length -gt 0 -and -not $content.EndsWith([Environment]::NewLine)) {
            $content += [Environment]::NewLine
        }
        $content += "$Name=$Value" + [Environment]::NewLine
    }
    Set-Content ".env" $content -Encoding UTF8
}

$generatedCreatorPassword = $null

if (-not (Get-DotEnvValue "APP_ENV")) {
    Set-DotEnvValue "APP_ENV" "development"
}

$secret = Get-DotEnvValue "APP_SECRET_KEY"
if (-not $secret -or $secret -eq "replace-me-with-a-secure-random-value") {
    $secret = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
    Set-DotEnvValue "APP_SECRET_KEY" $secret
}

if (-not (Get-DotEnvValue "CREATOR_BOOTSTRAP_USERNAME")) {
    Set-DotEnvValue "CREATOR_BOOTSTRAP_USERNAME" "creator"
}

$creatorPassword = Get-DotEnvValue "CREATOR_BOOTSTRAP_PASSWORD"
if (-not $creatorPassword -or $creatorPassword -eq "change-me-securely") {
    $creatorPassword = ([guid]::NewGuid().ToString("N") + "!Aa1")
    $generatedCreatorPassword = $creatorPassword
    Set-DotEnvValue "CREATOR_BOOTSTRAP_PASSWORD" $creatorPassword
}

if (-not (Get-DotEnvValue "DATABASE_URL")) {
    Set-DotEnvValue "DATABASE_URL" "postgresql+asyncpg://postgres:postgres@postgres:5432/the_creation_os"
}

if (-not (Get-DotEnvValue "REDIS_URL")) {
    Set-DotEnvValue "REDIS_URL" "redis://redis:6379/0"
}

$workerCredential = Get-DotEnvValue "WORKER_CREDENTIAL"
if (-not $workerCredential -or $workerCredential -eq "change-me-worker-securely") {
    $workerCredential = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
    Set-DotEnvValue "WORKER_CREDENTIAL" $workerCredential
}

if ($envCreated) {
    Write-Host "Created .env for the canonical local runtime."
} else {
    Write-Host "Validated and repaired local .env when required."
}
if ($generatedCreatorPassword) {
    Write-Host "Creator username: creator"
    Write-Host "Creator password: $generatedCreatorPassword"
    Write-Host "Store this password securely. It will not be printed again."
}

if ($Rebuild) {
    docker compose up -d --build
} else {
    docker compose up -d
}
if ($LASTEXITCODE -ne 0) {
    docker compose ps --all
    docker compose logs --no-color --tail=200
    throw "Docker Compose failed to start."
}

$deadline = (Get-Date).AddMinutes(2)
$checks = @(
    "http://127.0.0.1:8000/api/v1/health/ready",
    "http://127.0.0.1:8080/healthz",
    "http://127.0.0.1:8080/api/v1/health/ready"
)

do {
    $allHealthy = $true
    foreach ($url in $checks) {
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 4 | Out-Null
        } catch {
            $allHealthy = $false
            break
        }
    }
    if (-not $allHealthy) { Start-Sleep -Seconds 3 }
} until ($allHealthy -or (Get-Date) -ge $deadline)

if (-not $allHealthy) {
    docker compose ps --all
    docker compose logs --no-color --tail=200
    throw "Stack started but readiness checks did not become healthy."
}

$lanIp = Get-NetIPConfiguration |
    Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.IPv4Address -ne $null } |
    Select-Object -First 1 -ExpandProperty IPv4Address |
    Select-Object -ExpandProperty IPAddress

Write-Host ""
$bootstrapUsername = Get-DotEnvValue "CREATOR_BOOTSTRAP_USERNAME"
$bootstrapPassword = Get-DotEnvValue "CREATOR_BOOTSTRAP_PASSWORD"
if ($bootstrapUsername -and $bootstrapPassword) {
    $bootstrapBody = @{ username = $bootstrapUsername; password = $bootstrapPassword } | ConvertTo-Json
    try {
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/auth/bootstrap" -ContentType "application/json" -Body $bootstrapBody | Out-Null
        Write-Host "Creator bootstrap initialized."
    } catch {
        $statusCode = $null
        if ($_.Exception.Response) {
            try { $statusCode = [int]$_.Exception.Response.StatusCode } catch { }
        }
        if ($statusCode -ne 409) { throw }
        Write-Host "Creator bootstrap already exists."
    }
}

Write-Host "THE CREATION OS is healthy."
Write-Host "Local UI: http://localhost:8080"
if ($lanIp) {
    Write-Host ("LAN UI:   http://{0}:8080" -f $lanIp)
}
Write-Host "Local API health: http://127.0.0.1:8000/api/v1/health/ready"
Write-Host ""
Write-Host "PostgreSQL and Redis are private to the Docker network."
