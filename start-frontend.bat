@echo off
chcp 936 >/dev/null
title ZHQ-Frontend
cd /d "%~dp0web"
echo 正在启动前端 http://localhost:5173 ...
call npm run dev
pause
