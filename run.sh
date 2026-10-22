#!/usr/bin/env bash
# //Pranjal Das
# ==============================================================================
# Sentinel+ Launcher (run.sh)
# Starts the Alexa+ Streamable HTTP Model Context Protocol Server & Web Simulator
# ==============================================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$REPO_DIR:$REPO_DIR/packages:$PYTHONPATH"

# Dynamic Python 3.11 Discovery (Guarantees CPython 3.11 ABI isolation)
PYTHON_BIN=""
if command -v python3.11 &> /dev/null; then
    PYTHON_BIN="$(command -v python3.11)"
elif [ -f "/home/lowkeypranjal/.local/bin/python3.11" ]; then
    PYTHON_BIN="/home/lowkeypranjal/.local/bin/python3.11"
elif command -v python3 &> /dev/null; then
    PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")"
    if [ "$PY_VER" = "3.11" ]; then
        PYTHON_BIN="$(command -v python3)"
    fi
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Error: Python 3.11 is required to load compiled C-extensions in /packages."
    echo "   Please install Python 3.11 or add python3.11 to PATH."
    exit 1
fi

echo "================================================================="
echo "  🚀 Starting Sentinel+ Alexa MCP Server & Web Simulator"
echo "  📁 Working Directory: $REPO_DIR"
echo "  📦 Packages Source:   $REPO_DIR/packages (Drive D Exclusive)"
echo "  🐍 Python Binary:     $PYTHON_BIN"
echo "  🌐 Dashboard URL:     http://localhost:8000"
echo "================================================================="

# Pre-execution port audit (Rule [0] Sentry)
if ss -tulpn 2>/dev/null | grep -q ":8000 "; then
    echo "⚠️  Port 8000 is occupied. Auditing active process..."
    "$PYTHON_BIN" -m src.cli --check --ports 8000 || true
fi

# Launch Uvicorn cleanly without unconstrained DrvFs inotify watcher
exec "$PYTHON_BIN" -m uvicorn src.mcp_server:app --host 0.0.0.0 --port 8000
