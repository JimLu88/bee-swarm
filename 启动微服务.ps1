# 启动微服务.ps1 — 拉起 Computer Use 所需的 PC 侧微服务, 并注入第三方 LLM env
# 视觉(8006) + 键鼠(8008) + 代码手脚(8002) + 轻执行(8007)
# 用法: 右键“用 PowerShell 运行”, 或 双击 启动微服务.bat
$ErrorActionPreference = "Continue"
try { chcp 65001 > $null } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  蜂群 PC 侧微服务启动器 (Computer Use)" -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Cyan

# 1) 从 hub_settings.json 注入第三方 OpenAI 兼容网关 (让视觉 describe/locate 走第三方, 不用配 ANTHROPIC_API_KEY)
$hub = "D:\AI\AI 蜂群系统\h-semas\backend\data\hub_settings.json"
if (Test-Path $hub) {
    try {
        $cfg = Get-Content $hub -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cfg.openai_api_key)        { $env:OPENAI_API_KEY = $cfg.openai_api_key }
        if ($cfg.litellm_base_url)      { $env:OPENAI_API_BASE = $cfg.litellm_base_url; $env:OPENAI_BASE_URL = $cfg.litellm_base_url }
        Write-Host ("[env] 第三方网关: " + $env:OPENAI_API_BASE) -ForegroundColor Green
    } catch {
        Write-Host "[env] hub_settings.json 解析失败, 视觉语义理解(describe/locate)将不可用" -ForegroundColor Red
    }
} else {
    Write-Host "[env] 找不到 hub_settings.json, 视觉语义理解将走 501 兜底" -ForegroundColor Red
}

# 视觉 describe/locate 用快模型 (gemini-flash grounding 准且比 opus 快 4-6 倍); 外部已设则不覆盖
if (-not $env:BEE_VISION_MODEL) { $env:BEE_VISION_MODEL = "openai/gemini-3.5-flash" }
Write-Host ("[env] 视觉模型: " + $env:BEE_VISION_MODEL) -ForegroundColor Green

# 统一鉴权 token (须与主系统一致, 默认值与各服务一致)
if (-not $env:BEE_BEARER_TOKEN) { $env:BEE_BEARER_TOKEN = "50310b66f94f45eab17d13994b7b42361166c278" }
$env:PYTHONIOENCODING = "utf-8"
$env:BEE_VISION_URL = "http://127.0.0.1:8006"   # 键鼠服务失败时自动向视觉取图

$logDir = Join-Path $env:LOCALAPPDATA "bee-microservices"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$services = @(
    @{ name = "bee-vision  视觉 8006"; cwd = "D:\AI\AI 视觉中心\backend"; port = 8006 },
    @{ name = "bee-input   键鼠 8008"; cwd = "D:\AI\AI 键鼠服务\backend"; port = 8008 },
    @{ name = "bee-hands   手脚 8002"; cwd = "D:\AI\AI 代码手脚\backend"; port = 8002 },
    @{ name = "bee-light   轻执行 8007"; cwd = "D:\AI\AI 轻执行\backend"; port = 8007 }
)

foreach ($s in $services) {
    $out = Join-Path $logDir ("svc_" + $s.port + ".out.log")
    $err = Join-Path $logDir ("svc_" + $s.port + ".err.log")
    Start-Process -FilePath "py" `
        -ArgumentList @("-3.11", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$($s.port)") `
        -WorkingDirectory $s.cwd -WindowStyle Hidden `
        -RedirectStandardOutput $out -RedirectStandardError $err | Out-Null
    Write-Host ("启动 " + $s.name + " ...") -ForegroundColor Yellow
}

Write-Host "`n等待服务就绪 (约 6 秒)..." -ForegroundColor Gray
Start-Sleep -Seconds 6

Write-Host "`n--- 健康检查 ---" -ForegroundColor Cyan
$allOk = $true
foreach ($s in $services) {
    try {
        $r = Invoke-WebRequest -Uri ("http://127.0.0.1:" + $s.port + "/healthz") -TimeoutSec 4 -UseBasicParsing
        Write-Host ("[OK]  " + $s.name + "  HTTP " + $r.StatusCode) -ForegroundColor Green
    } catch {
        $allOk = $false
        Write-Host ("[XX]  " + $s.name + "  未就绪 -> 看日志 " + (Join-Path $logDir ("svc_" + $s.port + ".err.log"))) -ForegroundColor Red
    }
}

Write-Host ""
if ($allOk) {
    Write-Host "全部就绪. Computer Use 链路: 视觉(8006 截图/OCR/locate) + 键鼠(8008 点击/输入)" -ForegroundColor Green
} else {
    Write-Host "部分服务未起, 检查上面的日志路径." -ForegroundColor Yellow
}
Write-Host ("日志目录: " + $logDir) -ForegroundColor Gray
