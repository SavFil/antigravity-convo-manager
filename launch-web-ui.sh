#!/usr/bin/env bash
# Antigravity Conversation Manager — Web UI Launcher (macOS / Linux)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="$(which python3 || which python)"
if [ -z "$PYTHON_BIN" ]; then
    echo "Error: Python 3 is required but was not found in PATH."
    exit 1
fi

"$PYTHON_BIN" server.py "$@"
