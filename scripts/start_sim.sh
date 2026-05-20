#!/usr/bin/env bash
# Start the LO206 dyno simulator (Modbus TCP server wrapping the engine model).
set -euo pipefail

VENV="/opt/dyno-venv"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM_DIR="${REPO_ROOT}/simulator"

# Modbus listen address/port (must match what the OpenPLC master points at).
MODBUS_HOST="0.0.0.0"
MODBUS_PORT="502"

if [ ! -d "${VENV}" ]; then
    echo "ERROR: venv not found at ${VENV}. Run scripts/provision_vm.sh first." >&2
    exit 1
fi

# shellcheck disable=SC1091
source "${VENV}/bin/activate"

echo "Starting LO206 dyno simulator"
echo "  repo:        ${REPO_ROOT}"
echo "  python:      $(python --version 2>&1)"
echo "  Modbus TCP:  listening on ${MODBUS_HOST}:${MODBUS_PORT}"
echo "  (point the OpenPLC Modbus master at this host, port ${MODBUS_PORT})"

cd "${SIM_DIR}"
exec python modbus_server.py
