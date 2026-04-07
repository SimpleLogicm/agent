#!/bin/bash
set -e

echo ""
echo "============================================================"
echo "  AI Agent SDK - One Command Installer"
echo "  Installs everything and starts the agent."
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

# Install dependencies
echo "Installing dependencies..."
$PY -m pip install -r requirements.txt --quiet 2>/dev/null || $PY -m pip install -r requirements.txt
echo "[OK] Dependencies installed"

# Run setup (handles: license + DB config + Ollama + model + auto-starts agent)
echo ""
$PY setup.py "$@" < /dev/tty
