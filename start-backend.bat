@echo off
chcp 936 >/dev/null
title ZHQ-Backend
cd /d "%~dp0"
echo 正在启动后端 http://127.0.0.1:8000 ...
".venv\Scripts\python.exe" -m zhihui_qilu.main
pause
