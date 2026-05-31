@echo off
chcp 65001 > nul
cd /d "%~dp0"

REM 托盘看门狗 — 无控制台窗口, 跑在系统托盘
REM 如果 pystray/Pillow 缺, 先装一次
py -3.11 -c "import pystray, PIL" 2>nul
if errorlevel 1 (
    echo Installing pystray + Pillow ...
    py -3.11 -m pip install --quiet pystray pillow
)

REM pythonw.exe 跑 .pyw, 完全没控制台
start "" pythonw "%~dp0tray_watchdog.pyw"
