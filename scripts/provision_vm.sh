#!/usr/bin/env bash
#
# provision_vm.sh - reproduce the dyno-dev development environment.
#
# Idempotent: safe to re-run. Captures every step taken to set up the VM that
# stands in for the Raspberry Pi during sim-first development. Target OS:
# Ubuntu (developed against 24.04 LTS).
#
# Usage:  ./scripts/provision_vm.sh
#
set -euo pipefail

VENV="/opt/dyno-venv"
OPENPLC_DIR="${HOME}/OpenPLC_v3"

echo "==> Updating apt and installing system packages"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git \
    python3 python3-pip python3-venv \
    build-essential \
    curl wget net-tools

echo "==> Installing GitHub CLI (gh) from the official apt repo"
if ! command -v gh >/dev/null 2>&1; then
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
    sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
    sudo apt-get update -y
    sudo apt-get install -y gh
else
    echo "    gh already installed: $(gh --version | head -1)"
fi

echo "==> Creating Python venv at ${VENV} with sim dependencies"
if [ ! -d "${VENV}" ]; then
    sudo python3 -m venv "${VENV}"
fi
sudo "${VENV}/bin/pip" install --upgrade pip
sudo "${VENV}/bin/pip" install pymodbus numpy pytest

echo "==> Installing OpenPLC runtime"
if [ ! -d "${OPENPLC_DIR}" ]; then
    git clone https://github.com/thiagoralves/OpenPLC_v3.git "${OPENPLC_DIR}"
fi
if ! systemctl list-unit-files 2>/dev/null | grep -q '^openplc'; then
    ( cd "${OPENPLC_DIR}" && ./install.sh linux )
else
    echo "    OpenPLC service already present; skipping install.sh"
fi
sudo systemctl enable --now openplc || true

echo "==> Configuring git (EDIT these to the correct identity)"
git config --global user.name  "Bram Weitzman"
git config --global user.email "bram.weitzman@gmail.com"
git config --global init.defaultBranch main

echo "==> Done."
echo "    Python venv:    ${VENV}"
echo "    OpenPLC web UI:  http://<this-host>:8080  (systemctl status openplc)"
echo "    Activate sim:    source ${VENV}/bin/activate"
