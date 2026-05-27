# B2 packaging: export frontend to static files, copy into backend, build a Windows exe (PyInstaller).
# Run from repo root:  .\scripts\package-b2.ps1

param(
  [string]$Python = "py",
  [string]$PythonVer = "-3.11"
)

$ErrorActionPreference = "Continue"
# PowerShell 5.1 treats native command stderr as error stream under "Stop";
# pip / PyInstaller / npm write INFO lines to stderr by convention, so we use
# "Continue" and check $LASTEXITCODE explicitly after each invocation.
$PSNativeCommandUseErrorActionPreference = $false
$root = Split-Path -Parent $PSScriptRoot

Write-Host "=== H-SEMAS package B2 ===" -ForegroundColor Cyan
Write-Host "Root: $root`n"

Write-Host "[1/5] Frontend export (Next output=export) ..." -ForegroundColor Yellow
Push-Location (Join-Path $root "frontend")
try {
  npm install 2>&1 | Out-Host
  npm run export 2>&1 | Out-Host
} finally {
  Pop-Location
}

$frontendOut = Join-Path $root "frontend\out"
if (!(Test-Path $frontendOut)) {
  throw "frontend export output not found: $frontendOut"
}

Write-Host "`n[2/5] Copy static UI into backend/app/static_ui ..." -ForegroundColor Yellow
$dst = Join-Path $root "backend\app\static_ui"
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Copy-Item -Recurse -Force $frontendOut $dst

Write-Host "`n[3/5] Install backend deps + pyinstaller ..." -ForegroundColor Yellow
Push-Location (Join-Path $root "backend")
try {
  & $Python $PythonVer -m pip install -r requirements.txt 2>&1 | Out-Host
  & $Python $PythonVer -m pip install pyinstaller 2>&1 | Out-Host
} finally {
  Pop-Location
}

Write-Host "`n[4/5] Build exe (onefile) ..." -ForegroundColor Yellow
$exeOut = Join-Path $root "backend\dist\h-semas.exe"
if (Test-Path $exeOut) {
  try {
    Remove-Item -LiteralPath $exeOut -Force -ErrorAction Stop
  } catch {
    $bak = "$exeOut.bak.$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
    Write-Host "WARN: cannot delete locked exe (close running h-semas.exe). Renaming -> $bak" -ForegroundColor Yellow
    Move-Item -LiteralPath $exeOut -Destination $bak -Force
  }
}

Push-Location (Join-Path $root "backend")
try {
  $addData = "app\static_ui;app\static_ui"
  & $Python $PythonVer -m PyInstaller `
    --noconfirm `
    --onefile `
    --name "h-semas" `
    --add-data $addData `
    --collect-all "uvicorn" `
    --collect-all "fastapi" `
    --collect-all "pydantic" `
    --collect-all "pydantic_settings" `
    --collect-all "orjson" `
    --collect-all "httpx" `
    --collect-all "litellm" `
    --collect-all "tiktoken" `
    --hidden-import "tiktoken_ext.openai_public" `
    --collect-all "openai" `
    "hsemas_entry.py" 2>&1 | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed (exit $LASTEXITCODE). See backend\build\h-semas\warn-h-semas.txt"
  }
} finally {
  Pop-Location
}

if (!(Test-Path $exeOut)) {
  throw "EXE not found after build: $exeOut"
}
$len = (Get-Item -LiteralPath $exeOut).Length
if ($len -lt 1MB) {
  Write-Host "WARN: exe seems small ($len bytes); verify build output." -ForegroundColor Yellow
}

Write-Host "`n[5/5] Build launcher (tkinter tray-style window, no console) ..." -ForegroundColor Yellow
$launcherSrc = Join-Path $root "scripts\h_semas_launcher.py"
if (!(Test-Path $launcherSrc)) {
  throw "launcher script not found: $launcherSrc"
}
$launcherOut = Join-Path $root "backend\dist\h-semas-launcher.exe"
if (Test-Path $launcherOut) {
  try {
    Remove-Item -LiteralPath $launcherOut -Force -ErrorAction Stop
  } catch {
    $bak = "$launcherOut.bak.$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
    Write-Host "WARN: cannot delete locked launcher exe. Renaming -> $bak" -ForegroundColor Yellow
    Move-Item -LiteralPath $launcherOut -Destination $bak -Force
  }
}
Push-Location (Join-Path $root "backend")
try {
  $relLauncher = "..\scripts\h_semas_launcher.py"
  & $Python $PythonVer -m PyInstaller `
    --noconfirm `
    --onefile `
    --windowed `
    --name "h-semas-launcher" `
    $relLauncher 2>&1 | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller launcher failed (exit $LASTEXITCODE). See backend\build\h-semas-launcher\warn-h-semas-launcher.txt"
  }
} finally {
  Pop-Location
}
if (!(Test-Path $launcherOut)) {
  throw "Launcher EXE not found after build: $launcherOut"
}
$llen = (Get-Item -LiteralPath $launcherOut).Length

Write-Host "`nDone." -ForegroundColor Green
Write-Host "  Backend: $exeOut ($len bytes)" -ForegroundColor Green
Write-Host "  Launcher: $launcherOut ($llen bytes)" -ForegroundColor Green
Write-Host "  Tip: keep h-semas.exe and h-semas-launcher.exe in the same folder. Use launcher to Restart after code changes." -ForegroundColor Cyan

