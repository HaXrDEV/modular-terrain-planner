#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [ ! -f "$VENV/bin/python" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV" || { echo "Failed to create virtual environment. Is Python 3 installed?"; exit 1; }
fi

if [ ! -f "$VENV/bin/activate" ]; then
    echo "Virtual environment looks broken. Delete .venv and try again."
    exit 1
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

if ! python -c "import PySide6, stl, numpy, OpenGL" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r "$SCRIPT_DIR/requirements.txt" || { echo "Dependency installation failed."; exit 1; }
fi

python "$SCRIPT_DIR/main.py"
