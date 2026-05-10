param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 3000
)

$ErrorActionPreference = "Stop"

function Kill-Port([int]$Port) {
  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach ($c in $conns) {
    $procId = $c.OwningProcess
    if ($procId -and $procId -ne 0) {
      try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch {}
    }
  }
}

Write-Host "Killing listeners on ports $BackendPort, $FrontendPort ..."
Kill-Port -Port $BackendPort
Kill-Port -Port $FrontendPort

# Ensure UTF-8 output for Chinese logs
$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "Root: $root"
Write-Host "BackendPort=$BackendPort  FrontendPort=$FrontendPort"
Write-Host ""

Write-Host "Installing backend deps (pip) ..."
& py -3.11 -m pip install -r (Join-Path $root "backend\\requirements.txt") | Out-Host

Write-Host "Installing frontend deps (npm) ..."
Push-Location (Join-Path $root "frontend")
try {
  & npm install | Out-Host
} finally {
  Pop-Location
}

Write-Host "Starting backend on http://127.0.0.1:$BackendPort ..."
Start-Process -WorkingDirectory (Join-Path $root "backend") -FilePath "py" -ArgumentList @(
  "-3.11", "-m", "uvicorn", "app.main:app", "--reload", "--port", "$BackendPort"
) -WindowStyle Normal

Write-Host "Starting frontend on http://localhost:$FrontendPort ..."
Start-Process -WorkingDirectory (Join-Path $root "frontend") -FilePath "cmd" -ArgumentList @(
  "/c", "npm run dev -- -p " + $FrontendPort
) -WindowStyle Normal

Write-Host ""
Write-Host "Open:"
Write-Host "  Frontend: http://localhost:$FrontendPort"
Write-Host "  Backend : http://127.0.0.1:$BackendPort/api/health"

Write-Host ""
Write-Host "Tips:"
Write-Host "  - Backend logs will appear in the new Python window"
Write-Host "  - Frontend logs will appear in the new cmd window"

