#!/bin/bash
set -e

echo ""
echo "============================================================"
echo "  AI Agent SDK - Installer"
echo "  Install AI Agent in your project"
echo "============================================================"
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# 1. Check Python
echo "Checking Python..."
if command -v python3 &>/dev/null; then
    PY=$(command -v python3)
    success "Found $(python3 --version 2>&1)"
else
    fail "Python 3 not found. Install from https://python.org"
fi

# 2. Check pip
echo "Checking pip..."
if command -v pip3 &>/dev/null; then
    PIP="pip3"
elif $PY -m pip --version &>/dev/null; then
    PIP="$PY -m pip"
else
    fail "pip not found"
fi
success "Found pip"

# 3. Install dependencies
echo "Installing Python dependencies..."
$PIP install -r requirements.txt --quiet 2>/dev/null || $PIP install -r requirements.txt
success "Dependencies installed"

# 4. Check/Install Ollama
echo "Checking Ollama..."
if curl -s http://localhost:11434/api/tags &>/dev/null; then
    success "Ollama is running"
elif command -v ollama &>/dev/null; then
    warn "Ollama installed but not running. Start it before using the agent."
elif [ -f /Applications/Ollama.app/Contents/MacOS/Ollama ]; then
    warn "Ollama app found. Open it before using the agent."
else
    echo "Installing Ollama..."
    OS=$(uname -s)
    case "$OS" in
        Darwin) curl -fsSL https://ollama.com/install.sh | sh 2>/dev/null || warn "Install Ollama from https://ollama.com" ;;
        Linux)  curl -fsSL https://ollama.com/install.sh | sh || warn "Install Ollama from https://ollama.com" ;;
        *)      warn "Install Ollama manually: https://ollama.com/download" ;;
    esac
fi

# 5. Pull model if Ollama running
if curl -s http://localhost:11434/api/tags &>/dev/null; then
    MODELS=$(curl -s http://localhost:11434/api/tags)
    if echo "$MODELS" | grep -q "llama3"; then
        success "AI model available"
    else
        echo "Downloading AI model (one-time, ~2GB)..."
        ollama pull llama3.2:3b 2>/dev/null || warn "Pull model later: ollama pull llama3.2:3b"
    fi
fi

# 6. Run interactive setup
echo ""
echo "============================================================"
echo "  Starting interactive setup..."
echo "  You will need your Project Key and API Key from the platform."
echo "============================================================"
echo ""
python3 setup.py < /dev/tty
