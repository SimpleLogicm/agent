#!/bin/bash
set -e

echo ""
echo "============================================================"
echo "  AI Agent SDK - One-Click Installer"
echo "  This installs EVERYTHING you need"
echo "============================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

OS=$(uname -s)

# ─── Step 1: Check/Install Python ───
echo "[1/4] Checking Python..."
if command -v python3 &>/dev/null; then
    PY="python3"
    PIP="pip3"
elif command -v python &>/dev/null; then
    PY_VER=$(python -c "import sys; print(sys.version_info.major)")
    if [ "$PY_VER" = "3" ]; then
        PY="python"
        PIP="pip"
    else
        PY=""
    fi
fi

if [ -z "$PY" ]; then
    echo -e "  ${YELLOW}Python 3 not found. Installing...${NC}"
    if [ "$OS" = "Darwin" ]; then
        # macOS
        if ! command -v brew &>/dev/null; then
            echo "  Installing Homebrew first..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        brew install python
    elif [ "$OS" = "Linux" ]; then
        # Linux
        if command -v apt &>/dev/null; then
            sudo apt update
            sudo apt install -y python3 python3-pip python3-venv
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y python3 python3-pip
        elif command -v yum &>/dev/null; then
            sudo yum install -y python3 python3-pip
        elif command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm python python-pip
        else
            echo -e "  ${RED}Could not auto-install Python.${NC}"
            echo "  Please install Python 3.8+ from https://python.org"
            exit 1
        fi
    fi
    PY="python3"
    PIP="pip3"
fi
echo -e "  ${GREEN}[OK] $($PY --version 2>&1)${NC}"

# ─── Step 2: Check/Install Git ───
echo ""
echo "[2/4] Checking Git..."
if ! command -v git &>/dev/null; then
    echo -e "  ${YELLOW}Git not found. Installing...${NC}"
    if [ "$OS" = "Darwin" ]; then
        brew install git
    elif [ "$OS" = "Linux" ]; then
        if command -v apt &>/dev/null; then
            sudo apt install -y git
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y git
        elif command -v yum &>/dev/null; then
            sudo yum install -y git
        fi
    fi
fi
echo -e "  ${GREEN}[OK] Git $(git --version | awk '{print $3}')${NC}"

# ─── Step 3: Install Python dependencies ───
echo ""
echo "[3/4] Installing Python packages..."
$PY -m pip install --upgrade pip --quiet 2>/dev/null || true
$PY -m pip install -r requirements.txt --quiet 2>/dev/null || $PY -m pip install -r requirements.txt
echo -e "  ${GREEN}[OK] All packages installed${NC}"

# ─── Step 4: Run setup ───
echo ""
echo "[4/4] Starting interactive setup..."
echo "============================================================"
echo ""

if [ -t 0 ]; then
    $PY setup.py "$@"
else
    $PY setup.py "$@" < /dev/tty
fi
