@echo off
echo.
echo ============================================================
echo   AI Agent SDK - Windows Installer
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
pip install -r requirements.txt -q
echo [OK] Dependencies installed

echo.
echo ============================================================
echo   Enter your keys and database details below.
echo   Everything else is automatic.
echo ============================================================
echo.
python setup.py %*
