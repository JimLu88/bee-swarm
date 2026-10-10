# deploy.ps1 — H-SEMAS 一键部署 (PC → 群晖)
# 用法:
#   .\deploy.ps1                # 校验 + 把 git 已改动的 backend/frontend 文件 scp 到 NAS + rebuild + 验证
#   .\deploy.ps1 -NoBuild       # 只传文件不 rebuild (改 .md/数据等)
#   .\deploy.ps1 -Files a.py,b.tsx  # 指定文件(相对仓库根)
# 流程: py_compile → tsc --noEmit → scp /tmp → sudo cp → docker compose up -d --build backend → healthz
# 说明: 当前 NAS 工作区与 git 历史脱节(双脏), 故用 scp 覆盖模式; 收编进 git 后可切回 deploy/update.sh。
param(
    [string[]]$Files = @(),
    [switch]$NoBuild,
    [string]$NasUser = "15068803006",
    [string]$NasHost = "192.168.31.21",
    [string]$NasRepo = "/volume1/docker/h-semas"
)
$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$py = "C:\Users\lzdwy\AppData\Local\Programs\Python\Python311\python.exe"

# 1) 取改动清单 (未指定时 = git 已修改/新增的 backend|frontend 代码文件)
if (-not $Files -or $Files.Count -eq 0) {
    $Files = git -C $repo status --short |
        ForEach-Object { ($_ -replace '^...', '').Trim('"') } |
        Where-Object { $_ -match '^(backend|frontend)/' -and $_ -match '\.(py|tsx|ts|css|json|yaml)$' -and $_ -notmatch 'data/' }
}
if (-not $Files -or $Files.Count -eq 0) { Write-Host "没有可部署的改动文件" -ForegroundColor Yellow; exit 0 }
Write-Host "== 部署清单 ($($Files.Count)) ==" -ForegroundColor Cyan
$Files | ForEach-Object { Write-Host "  $_" }

# 2) 校验
$pyFiles = $Files | Where-Object { $_ -match '\.py$' } | ForEach-Object { Join-Path $repo $_ }
if ($pyFiles) {
    & $py -m py_compile @pyFiles
    if (-not $?) { Write-Host "py_compile 失败, 中止" -ForegroundColor Red; exit 1 }
    Write-Host "py_compile OK" -ForegroundColor Green
}
if ($Files | Where-Object { $_ -match '\.(tsx|ts)$' }) {
    Push-Location (Join-Path $repo "frontend")
    $tsc = & npx tsc --noEmit 2>&1
    Pop-Location
    $tsErr = ($tsc | Select-String "error TS").Count
    if ($tsErr -gt 0) { Write-Host "tsc $tsErr 个错误, 中止:" -ForegroundColor Red; $tsc | Select-String "error TS" | Select-Object -First 5; exit 1 }
    Write-Host "tsc OK" -ForegroundColor Green
}

# 3) 传输 (scp → /tmp → sudo cp 到位; 保持目录结构)
$local = $Files | ForEach-Object { Join-Path $repo $_ }
scp -O @local "${NasUser}@${NasHost}:/tmp/" | Out-Null
if (-not $?) { Write-Host "scp 失败" -ForegroundColor Red; exit 1 }
$cps = ($Files | ForEach-Object {
    $name = Split-Path $_ -Leaf
    $dest = "$NasRepo/$($_ -replace '\\','/')"
    "sudo cp '/tmp/$name' '$dest'"
}) -join " && "
ssh "${NasUser}@${NasHost}" "$cps && echo COPIED"
if (-not $?) { Write-Host "远端 cp 失败" -ForegroundColor Red; exit 1 }

# 4) rebuild + 验证
if (-not $NoBuild) {
    Write-Host "== rebuild backend (1-3 分钟) ==" -ForegroundColor Cyan
    ssh "${NasUser}@${NasHost}" "cd $NasRepo && sudo /usr/local/bin/docker compose up -d --build backend 2>&1 | tail -3"
    Start-Sleep -Seconds 8
    try {
        $code = (Invoke-WebRequest "http://${NasHost}:8100/api/dev/paused" -TimeoutSec 10 -UseBasicParsing -ErrorAction SilentlyContinue).StatusCode
    } catch { $code = $_.Exception.Response.StatusCode.value__ }
    if ($code -in 200, 401) { Write-Host "✅ backend 存活 (HTTP $code)" -ForegroundColor Green }
    else { Write-Host "⚠ backend 健康检查异常 (HTTP $code) — 去看 docker compose logs backend" -ForegroundColor Red; exit 1 }
}
Write-Host "✅ 部署完成 $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Green
Write-Host "提醒: 记得把改动 commit + push 到 GitHub 留档 (git add <files> && git commit && git push)"
