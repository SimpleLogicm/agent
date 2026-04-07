@echo off
echo.
echo ============================================================
echo   AI Agent SDK - Windows Installer
echo   Install AI Agent in your project
echo ============================================================
echo.

echo Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Install from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found

echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo [OK] Dependencies installed

echo.
echo ============================================================
echo   Starting setup...
echo ============================================================
echo.
python setup.py

pause
