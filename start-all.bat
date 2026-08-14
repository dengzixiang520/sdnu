@echo off
echo Starting services...
start "Backend" /D "D:\study-race\race\SDNU人工智能\zhihui_qilu" cmd /k "set PYTHONPATH=src && python -m zhihui_qilu.main"
start "Frontend" /D "D:\study-race\race\SDNU人工智能\zhihui_qilu\web" cmd /k "npm run dev"
echo Services started!
echo Backend: http://127.0.0.1:8000
echo Frontend: http://localhost:5173
pause