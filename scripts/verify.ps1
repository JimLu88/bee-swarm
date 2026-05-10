# One-shot CI-style check: backend unit tests + frontend lint + production build.
# Run from repo root:  .\scripts\verify.ps1

param(
  [string]$Python = "py",
  [string]$PythonVer = "-3.11"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "=== H-SEMAS verify ===" -ForegroundColor Cyan
Write-Host "Root: $root`n"

Write-Host "[1/3] Backend unittest ..." -ForegroundColor Yellow
Push-Location (Join-Path $root "backend")
try {
  & $Python $PythonVer -m unittest discover -s tests -v
  if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: unittest exit $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
  }
} finally {
  Pop-Location
}

Write-Host "`n[2/3] Frontend eslint (next lint) ..." -ForegroundColor Yellow
Push-Location (Join-Path $root "frontend")
try {
  npm run lint
  if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: npm lint exit $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
  }
} finally {
  Pop-Location
}

Write-Host "`n[3/3] Frontend next build ..." -ForegroundColor Yellow
Push-Location (Join-Path $root "frontend")
try {
  npm run build
  if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: npm build exit $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
  }
} finally {
  Pop-Location
}

Write-Host "`n=== OK verify ===" -ForegroundColor Green
