@echo off
chcp 65001 > nul
echo 关闭蜂群前后端...
taskkill /FI "WindowTitle eq 蜂群后端*" /F
taskkill /FI "WindowTitle eq 蜂群前端*" /F
echo 已关闭. 按任意键退出.
pause > nul