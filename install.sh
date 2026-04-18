#!/bin/bash
set -e

echo ""
echo "============================================================"
echo "  AI Agent SDK - Installer"
echo "  Just enter your keys - no AI model download needed!"
echo "============================================================"
echo ""

# Check Python
if command -v python3 &>/dev/null; then
    PY="python3"
elif command -v python &>/dev/null; then
    PY="python"
else
    echo "[ERROR] Python not found. Install from https://python.org"
    exit 1
fi
echo "[OK] Found $($PY --version 2>&1)"

# Install dependencies (much lighter - no Ollama!)
echo "Installing dependencies..."
$PY -m pip install -r requirements.txt --quiet 2>/dev/null || $PY -m pip install -r requirements.txt
echo "[OK] Dependencies installed"

echo ""
$PY setup.py "$@" < /dev/tty
