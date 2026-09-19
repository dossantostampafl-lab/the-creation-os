<#
.SYNOPSIS
  Creates the ./secrets/*.txt files docker-compose.yml expects, if they are
  missing. Safe to re-run: existing non-empty files are left untouched
  unless -Force is passed.

.EXAMPLE
  ./scripts/generate-secrets.ps1
  ./scripts/generate-secrets.ps1 -Force
#>
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$secretsDir = Join-Path $repoRoot "secrets"

if (-not (Test-Path $secretsDir)) {
    New-Item -ItemType Directory -Path $secretsDir | Out-Null
}

function New-RandomHex([int]$bytes) {
    $buffer = New-Object byte[] $bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($buffer)
    } finally {
        $rng.Dispose()
    }
    return ($buffer | ForEach-Object { $_.ToString("x2") }) -join ""
}

function Write-SecretFile([string]$name, [string]$content) {
    $path = Join-Path $secretsDir $name
    if ((Test-Path $path) -and -not $Force -and (Get-Item $path).Length -gt 0) {
        Write-Host "skip   $name (already exists, use -Force to overwrite)"
        return
    }
    # No trailing newline: config.py reads these files verbatim (rstrip only \r\n).
    [System.IO.File]::WriteAllText($path, $content)
    Write-Host "wrote  $name"
}

$postgresPassword = New-RandomHex 32

Write-SecretFile "app_secret_key.txt" (New-RandomHex 32)
Write-SecretFile "creator_bootstrap_password.txt" (New-RandomHex 16)
Write-SecretFile "postgres_password.txt" $postgresPassword
Write-SecretFile "database_url.txt" "postgresql+asyncpg://postgres:$postgresPassword@postgres:5432/the_creation_os"
Write-SecretFile "worker_credential.txt" (New-RandomHex 32)

# Optional integrations (LLM, embeddings via fake providers by default; GitHub/ElevenLabs
# unset). Left empty on purpose - never fabricate a placeholder that looks like a real key.
foreach ($optional in @("elevenlabs_api_key.txt", "github_token.txt", "llm_api_key.txt")) {
    $path = Join-Path $secretsDir $optional
    if (-not (Test-Path $path)) {
        New-Item -ItemType File -Path $path | Out-Null
        Write-Host "wrote  $optional (empty - fill in only if the integration is enabled)"
    } else {
        Write-Host "skip   $optional (already exists)"
    }
}

Write-Host ""
Write-Host "secrets/ ready. postgres_password.txt and database_url.txt share the same password."
