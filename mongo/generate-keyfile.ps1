$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$secretDirectory = Join-Path $repoRoot "secrets"
$keyfilePath = Join-Path $secretDirectory "mongo-keyfile"

New-Item -ItemType Directory -Force -Path $secretDirectory | Out-Null

if (Test-Path -LiteralPath $keyfilePath) {
    Write-Host "MongoDB keyfile already exists: $keyfilePath"
    exit 0
}

$bytes = New-Object byte[] 756
$generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $generator.GetBytes($bytes)
} finally {
    $generator.Dispose()
}
$key = [Convert]::ToBase64String($bytes)
[System.IO.File]::WriteAllText($keyfilePath, $key + "`n", [System.Text.UTF8Encoding]::new($false))
Write-Host "Generated MongoDB keyfile: $keyfilePath"

