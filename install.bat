@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   AI Agent SDK - One-Click Installer
echo   This installs EVERYTHING you need
echo ============================================================
echo.

REM ─── Step 1: Check/Install Python ───
echo [1/4] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Python not found. Downloading installer...
    echo   This will open a browser window - please install Python
    echo   IMPORTANT: Check "Add Python to PATH" during install!
    echo.
    start https://www.python.org/downloads/
    echo.
    echo   After installing Python, close this window and run install.bat again
    pause
    exit /b 1
)

for /f "tokens=2" %%I in ('python --version 2^>^&1') do set PY_VER=%%I
echo   [OK] Python !PY_VER! found

REM ─── Step 2: Check/Install Git ───
echo.
echo [2/4] Checking Git...
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Git not found. Opening download page...
    start https://git-scm.com/download/win
    echo.
    echo   After installing Git, close this window and run install.bat again
    pause
    exit /b 1
)
echo   [OK] Git found

REM ─── Step 3: Install Python dependencies ───
echo.
echo [3/4] Installing Python packages...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install packages
    pause
    exit /b 1
)
echo   [OK] All packages installed

REM ─── Step 4: Run setup ───
echo.
echo [4/4] Starting interactive setup...
echo ============================================================
echo.
python setup.py %*

pause
