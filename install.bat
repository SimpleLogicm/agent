@echo off
echo.
echo ============================================================
echo   AI Agent SDK - Windows Installer
echo   Just enter your keys - no AI model download needed!
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
python setup.py %*
