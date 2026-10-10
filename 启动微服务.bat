@echo off
chcp 65001 > nul
title 蜂群 PC 侧微服务 (Computer Use)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0启动微服务.ps1"
echo.
echo (服务已在后台运行. 此窗口可关闭. 关服务用任务管理器结束 python 进程)
pause
