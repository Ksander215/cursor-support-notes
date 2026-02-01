#!/bin/bash
# Setup script for pre-commit hooks

set -e

echo "🔧 Setting up pre-commit hooks..."

# Function to find and use the right Python/pip
setup_python_env() {
    # Check if we're in a virtual environment
    if [ -n "$VIRTUAL_ENV" ]; then
        echo "✅ Using active virtual environment: $VIRTUAL_ENV"
        PIP_CMD="pip"
        PYTHON_CMD="python"
        return 0
    fi

    # Check for .venv in project root
    if [ -f ".venv/bin/activate" ]; then
        echo "📦 Activating virtual environment .venv..."
        source .venv/bin/activate
        PIP_CMD="pip"
        PYTHON_CMD="python"
        return 0
    fi

    # Check if pipx is available (best option for pre-commit)
    if command -v pipx &> /dev/null; then
        echo "📦 Using pipx to install pre-commit (recommended)..."
        PIP_CMD="pipx"
        PYTHON_CMD="python3"
        return 0
    fi

    # Try to use python3 -m pip (works in some cases)
    if command -v python3 &> /dev/null; then
        echo "⚠️  No virtual environment found. Trying python3 -m pip..."
        PIP_CMD="python3 -m pip"
        PYTHON_CMD="python3"
        return 0
    fi

    echo "❌ Error: Could not find Python environment"
    echo ""
    echo "Please choose one of the following options:"
    echo "1. Create virtual environment: python3 -m venv .venv && source .venv/bin/activate"
    echo "2. Install pipx: sudo apt install pipx && pipx ensurepath"
    echo "3. Use existing venv: source .venv/bin/activate"
    exit 1
}

# Setup Python environment
setup_python_env

# Check if pre-commit is installed
if ! command -v pre-commit &> /dev/null; then
    echo "📦 Installing pre-commit..."
    if [ "$PIP_CMD" = "pipx" ]; then
        pipx install pre-commit
        # Add pipx bin to PATH if needed
        export PATH="$HOME/.local/bin:$PATH"
    else
        $PIP_CMD install pre-commit
    fi
fi

# Verify pre-commit is available
if ! command -v pre-commit &> /dev/null; then
    echo "❌ Error: pre-commit is not in PATH"
    if [ "$PIP_CMD" = "pipx" ]; then
        echo "💡 Try: export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
    exit 1
fi

# Install pre-commit hooks
echo "📝 Installing pre-commit hooks..."
pre-commit install

# Create secrets baseline if it doesn't exist
if [ ! -f .secrets.baseline ]; then
    echo "🔐 Creating secrets baseline..."
    if command -v detect-secrets &> /dev/null; then
        detect-secrets scan --baseline .secrets.baseline || {
            echo "⚠️ Could not create secrets baseline. Continuing without it..."
        }
    else
        echo "⚠️ detect-secrets not found. Install it with: pip install detect-secrets"
        echo "   Or create baseline manually: detect-secrets scan --baseline .secrets.baseline"
    fi
fi

# Run pre-commit on all files to check setup
echo "✅ Running pre-commit on all files (this may take a while)..."
pre-commit run --all-files || {
    echo "⚠️ Some checks failed. Please review and fix the issues."
    echo "💡 You can skip hooks for this commit with: git commit --no-verify"
    exit 1
}

echo "✅ Pre-commit hooks setup complete!"
echo ""
echo "💡 Tips:"
echo "  - Hooks will run automatically on 'git commit'"
echo "  - Run manually: pre-commit run --all-files"
echo "  - Update hooks: pre-commit autoupdate"
echo "  - Skip hooks: git commit --no-verify"
