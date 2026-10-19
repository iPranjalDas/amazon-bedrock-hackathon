#!/usr/bin/env bash
# //Pranjal Das
# ==============================================================================
# Sentinel+ Launcher (run.sh)
# Starts the Alexa+ Streamable HTTP Model Context Protocol Server & Web Simulator
# ==============================================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$REPO_DIR:$REPO_DIR/packages:$PYTHONPATH"

PYTHON_BIN="/home/lowkeypranjal/.local/bin/python3.11"
if ! command -v "$PYTHON_BIN" &> /dev/null; then
    PYTHON_BIN="python3"
fi

echo "================================================================="
echo "  🚀 Starting Sentinel+ Alexa MCP Server & Web Simulator"
echo "  📁 Working Directory: $REPO_DIR"
echo "  📦 Packages Source:   $REPO_DIR/packages (Drive D Exclusive)"
echo "  🌐 Dashboard URL:     http://localhost:8000"
echo "================================================================="

# Pre-execution port audit (Rule [0])
if ss -tulpn | grep -q ":8000 "; then
    echo "⚠️  Port 8000 is occupied. Auditing process..."
    "$PYTHON_BIN" -m src.cli --check --ports 8000
fi

exec "$PYTHON_BIN" -m uvicorn src.mcp_server:app --host 0.0.0.0 --port 8000 --reload
