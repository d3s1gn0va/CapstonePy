#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${PI_HOST:?Set PI_HOST to the authorized SSH destination}"
: "${SSH_KEY:?Set SSH_KEY to the existing private key path}"
REMOTE_BLE_DIR="${REMOTE_BLE_DIR:-capstone-robot-build/ble_control_20261006/robot_demo}"

if [[ ! "$REMOTE_BLE_DIR" =~ ^[a-zA-Z0-9_/-]+$ || "$REMOTE_BLE_DIR" == *..* || "$REMOTE_BLE_DIR" == /* ]]; then
  printf '%s\n' 'REMOTE_BLE_DIR must be a safe path relative to the Pi home directory.' >&2
  exit 2
fi

bash "$PROJECT_ROOT/scripts/check_python.sh"
ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes "$PI_HOST" "mkdir -p '$REMOTE_BLE_DIR'"
rsync -av --checksum \
  --exclude '._*' --exclude '.DS_Store' \
  --include '/audio/' --include '/audio/*.wav' \
  --include '/*.py' --include '/*.json' --exclude '*' \
  -e "ssh -i $SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=yes" \
  "$PROJECT_ROOT/raspberry_pi/robot_demo/" "$PI_HOST:$REMOTE_BLE_DIR/"

printf '%s\n' 'BLE files copied only. No service start, servo motion, firmware upload, or autostart change.'
