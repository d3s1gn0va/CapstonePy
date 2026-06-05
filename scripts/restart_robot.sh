#!/usr/bin/env bash
set -euo pipefail

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"

ssh -i "$SSH_KEY" "$PI_HOST" "bash -lc '
set -euo pipefail
if systemctl --user list-unit-files robot-demo.service >/dev/null 2>&1; then
  systemctl --user restart robot-demo.service
  systemctl --user --no-pager status robot-demo.service || true
elif systemctl list-unit-files robot-demo.service >/dev/null 2>&1; then
  sudo systemctl restart robot-demo.service
  sudo systemctl --no-pager status robot-demo.service || true
else
  echo \"robot-demo.service is not installed yet.\"
  echo \"Current robot-related processes:\"
  pgrep -af \"python.*robot_demo|python.*main.py\" || true
  echo \"Autostart method is not confirmed, so no new startup method was enabled.\"
fi
'"
