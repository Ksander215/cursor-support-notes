#!/bin/bash
# Simple script to install pre-commit using the best available method

set -e

echo "🔧 Installing pre-commit..."

# Check if we're in a virtual environment
if [ -n "$VIRTUAL_ENV" ]; then
    echo "✅ Using active virtual environment: $VIRTUAL_ENV"
    pip install pre-commit
    pre-commit install
    echo "✅ Pre-commit installed successfully!"
    exit 0
fi

# Check for .venv
if [ -f ".venv/bin/activate" ]; then
    echo "📦 Activating virtual environment..."
    source .venv/bin/activate
    pip install pre-commit
    pre-commit install
    echo "✅ Pre-commit installed successfully!"
    exit 0
fi

# Check for pipx
if command -v pipx &> /dev/null; then
    echo "📦 Using pipx to install pre-commit..."
    pipx install pre-commit
    export PATH="$HOME/.local/bin:$PATH"
    pre-commit install
    echo "✅ Pre-commit installed successfully!"
    exit 0
fi

# Last resort: try python3 -m pip with user flag
if command -v python3 &> /dev/null; then
    echo "⚠️  No virtual environment found. Installing to user directory..."
    python3 -m pip install --user pre-commit
    export PATH="$HOME/.local/bin:$PATH"
    pre-commit install
    echo "✅ Pre-commit installed successfully!"
    exit 0
fi

echo "❌ Error: Could not find Python or pip"
echo ""
echo "Please install Python or create a virtual environment:"
echo "  python3 -m venv .venv"
echo "  source .venv/bin/activate"
exit 1
