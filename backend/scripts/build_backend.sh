#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PYTHONPATH="${BACKEND_DIR}"

echo "========================================"
echo "Building Agent Factory backend..."
echo "Working directory: ${BACKEND_DIR}"
echo "PYTHONPATH: ${PYTHONPATH}"
echo "========================================"

cd "${BACKEND_DIR}"
"${BACKEND_DIR}/.venv/bin/python" -m PyInstaller agent-factory.spec --clean --noconfirm

echo "========================================"
echo "Build complete."
echo "Output: ${BACKEND_DIR}/dist/agent-factory-backend"
echo "========================================"
