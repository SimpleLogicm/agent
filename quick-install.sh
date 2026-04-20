#!/bin/bash
# AI Agent SDK - Ultimate One-Liner Installer
# Usage: curl -sSL https://raw.githubusercontent.com/SimpleLogicm/agent/main/quick-install.sh | bash
#
# This clones the repo, installs everything, and runs setup - ONE COMMAND

set -e

echo ""
echo "============================================================"
echo "  AI Agent SDK - Quick Install"
echo "============================================================"
echo ""

OS=$(uname -s)

# Install Git if missing
if ! command -v git &>/dev/null; then
    echo "Installing Git..."
    if [ "$OS" = "Darwin" ]; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" 2>/dev/null || true
        brew install git
    else
        sudo apt install -y git 2>/dev/null || sudo dnf install -y git 2>/dev/null || sudo yum install -y git
    fi
fi

# Install Python if missing
if ! command -v python3 &>/dev/null; then
    echo "Installing Python..."
    if [ "$OS" = "Darwin" ]; then
        brew install python
    else
        sudo apt install -y python3 python3-pip 2>/dev/null || sudo dnf install -y python3 python3-pip 2>/dev/null || sudo yum install -y python3 python3-pip
    fi
fi

# Clone repo
if [ ! -d "agent" ]; then
    git clone https://github.com/SimpleLogicm/agent.git
fi
cd agent

# Run main installer
chmod +x install.sh
./install.sh
