@echo off
chcp 65001 > nul
cd /d "%~dp0"
title BEE Watchdog
py -3.11 watchdog.py
echo.
echo Watchdog exited. Press any key to close.
pause > nul