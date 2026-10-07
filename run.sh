#!/bin/bash
# One-command launcher for Renewable Energy Orchestrator
# Use absolute paths so this works regardless of where it's called from.
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "==> Working directory: $SCRIPT_DIR"
echo "==> Installing Python dependencies..."
pip3 install --quiet --disable-pip-version-check fastapi "uvicorn[standard]" websockets "pulp<3" numpy pydantic python-multipart 2>/dev/null || \
pip install --quiet --disable-pip-version-check fastapi "uvicorn[standard]" websockets "pulp<3" numpy pydantic python-multipart

echo "==> Installing frontend dependencies..."
cd "$SCRIPT_DIR/frontend"
npm install --no-audit --no-fund --silent

echo "==> Building frontend..."
npm run build 2>&1 | grep -v "code-split\|codeSplitting\|chunkSizeWarning" | tail -5

echo "==> Starting server on port 8000..."
echo "    Open your browser at:  http://localhost:8000"
echo "    (Press Ctrl+C to stop)"
echo ""
cd "$SCRIPT_DIR/backend"
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
