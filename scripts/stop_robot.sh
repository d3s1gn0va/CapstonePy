#!/usr/bin/env bash
set -euo pipefail

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"

ssh -i "$SSH_KEY" "$PI_HOST" "bash -lc '
set -euo pipefail
if systemctl --user list-unit-files robot-demo.service >/dev/null 2>&1; then
  systemctl --user stop robot-demo.service
elif systemctl list-unit-files robot-demo.service >/dev/null 2>&1; then
  sudo systemctl stop robot-demo.service
else
  pkill -f \"python.*$REMOTE_ROBOT_DIR|python.*main.py\" || true
  echo \"Stopped matching robot Python processes if any were running.\"
fi
'"
