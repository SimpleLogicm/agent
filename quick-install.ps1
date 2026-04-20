# AI Agent SDK - Windows One-Liner Installer
# Usage: iwr -useb https://raw.githubusercontent.com/SimpleLogicm/agent/main/quick-install.ps1 | iex
#
# This installs Python (via winget), Git, clones the repo, installs dependencies, runs setup

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AI Agent SDK - Windows Quick Install" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ─── Step 1: Check winget ───
Write-Host "[1/5] Checking winget (Windows Package Manager)..." -ForegroundColor Yellow
$wingetCheck = Get-Command winget -ErrorAction SilentlyContinue
if (-not $wingetCheck) {
    Write-Host "  winget not found. Please install 'App Installer' from Microsoft Store." -ForegroundColor Red
    Write-Host "  Opening Microsoft Store..." -ForegroundColor Yellow
    Start-Process "ms-windows-store://pdp/?productid=9nblggh4nns1"
    Write-Host "  After installing, re-run this script." -ForegroundColor Yellow
    exit 1
}
Write-Host "  [OK] winget found" -ForegroundColor Green

# ─── Step 2: Install Python if missing ───
Write-Host ""
Write-Host "[2/5] Checking Python..." -ForegroundColor Yellow
$pythonCheck = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCheck) {
    Write-Host "  Python not found. Installing via winget..." -ForegroundColor Yellow
    winget install --id Python.Python.3.11 --silent --accept-source-agreements --accept-package-agreements
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-Host "  [OK] Python installed" -ForegroundColor Green
    Write-Host "  NOTE: You may need to close this window and open a new PowerShell" -ForegroundColor Yellow
} else {
    Write-Host "  [OK] Python found: $(python --version 2>&1)" -ForegroundColor Green
}

# ─── Step 3: Install Git if missing ───
Write-Host ""
Write-Host "[3/5] Checking Git..." -ForegroundColor Yellow
$gitCheck = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCheck) {
    Write-Host "  Git not found. Installing via winget..." -ForegroundColor Yellow
    winget install --id Git.Git --silent --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    Write-Host "  [OK] Git installed" -ForegroundColor Green
} else {
    Write-Host "  [OK] Git found: $(git --version)" -ForegroundColor Green
}

# ─── Step 4: Clone repo ───
Write-Host ""
Write-Host "[4/5] Cloning AI Agent repo..." -ForegroundColor Yellow
if (Test-Path "agent") {
    Write-Host "  'agent' folder already exists. Updating..." -ForegroundColor Yellow
    Set-Location agent
    git pull
} else {
    git clone https://github.com/SimpleLogicm/agent.git
    Set-Location agent
}
Write-Host "  [OK] Repo ready" -ForegroundColor Green

# ─── Step 5: Install dependencies and setup ───
Write-Host ""
Write-Host "[5/5] Installing dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
Write-Host "  [OK] Packages installed" -ForegroundColor Green

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Starting interactive setup..." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

python setup.py
