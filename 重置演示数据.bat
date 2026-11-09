@echo off
chcp 936 >nul
setlocal
title 重置演示数据 - 智汇齐鲁·全域同频

set "ROOT=%~dp0"
set "PY=%ROOT%runtime\python\python.exe"

echo ============================================================
echo    重置演示数据
echo ============================================================
echo.
echo    会把以下内容恢复到演示基线：
echo      积分与打卡记录、兑换商品库存与兑换记录、
echo      已保存课表、三层记忆数据库
echo.

if not exist "%PY%" (
    echo [错误] 未找到便携版 Python: %PY%
    echo        请先成功运行一次 启动.bat，再使用本脚本。
    echo.
    pause
    exit /b 1
)

choice /c YN /n /m "确认重置请输入 Y，放弃请输入 N："
if errorlevel 2 (
    echo.
    echo 已取消，数据未改动。
    pause
    exit /b 0
)
echo.

"%PY%" "%ROOT%reset_demo_data.py"
echo.
echo 提示：若服务正在运行，请关闭 ZHQ-Backend 窗口后重新启动，改动才会生效。
echo.
pause
exit /b 0