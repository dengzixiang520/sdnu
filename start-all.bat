@echo off
echo ========================================
echo   智汇齐鲁 - 服务启动脚本
echo ========================================
echo.

echo [1/2] Starting backend...
start "Backend" cmd /c "cd /d D:\study-race\race\SDNU人工智能\zhihui_qilu && set PYTHONPATH=src && python -m zhihui_qilu.main"

echo [2/2] Starting frontend...
start "Frontend" cmd /c "cd /d D:\study-race\race\SDNU人工智能\zhihui_qilu\web && npm run dev"

echo.
echo Both services are starting...
echo Backend: http://127.0.0.1:8000
echo Frontend: http://localhost:5173
echo.
echo Press any key to exit this window (services will keep running)
pause >nul