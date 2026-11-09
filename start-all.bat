@echo off
chcp 936 >/dev/null
title ZHQ-启动器
cd /d "%~dp0"
echo 正在启动后端与前端 ...
start "ZHQ-Backend" /D "%~dp0" cmd /k ".venv\Scripts\python.exe -m zhihui_qilu.main"
start "ZHQ-Frontend" /D "%~dp0web" cmd /k "npm run dev"
echo.
echo 后端: http://127.0.0.1:8000/docs
echo 前端: http://localhost:5173
echo.
echo 提示: 推荐直接双击「启动.bat」，它会自动等待服务就绪并打开浏览器。
pause
