@echo off
chcp 65001 > nul
title ?? 蜂群系统 - 前后端

echo ============================================
echo  ?? 蜂群系统 - 一键启动
echo ============================================
echo.
echo [1/2] 启动后端 (端口 8100)...
start "蜂群后端" /MIN cmd /k "cd /d D:\AI\AI 蜂群系统\h-semas\backend && set PYTHONIOENCODING=utf-8 && py -3.11 -m uvicorn app.main:app --port 8100"

echo [2/2] 启动前端 (端口 4000)...
start "蜂群前端" /MIN cmd /k "cd /d D:\AI\AI 蜂群系统\h-semas\frontend && set PORT=4000 && npm run dev"

echo.
echo ============================================
echo  ? 两个窗口已最小化到任务栏 (别关!)
echo  浏览器打开: http://localhost:4000
echo ============================================
echo.
echo 等 15 秒后自动开浏览器...
timeout /t 15 /nobreak > nul
start http://localhost:4000

echo.
echo 这个窗口可以关. 后端和前端继续在最小化窗口里跑.
pause