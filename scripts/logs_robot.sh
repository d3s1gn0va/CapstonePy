#!/usr/bin/env bash
set -euo pipefail

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"

ssh -i "$SSH_KEY" "$PI_HOST" "bash -lc '
set -euo pipefail
if [ -f \"$REMOTE_ROBOT_DIR/robot_demo.log\" ]; then
  tail -f \"$REMOTE_ROBOT_DIR/robot_demo.log\"
elif systemctl --user --quiet is-active robot-demo.service 2>/dev/null; then
  journalctl --user -u robot-demo.service -f
elif systemctl --quiet is-active robot-demo.service 2>/dev/null; then
  journalctl -u robot-demo.service -f
else
  echo \"No robot log file or active robot-demo.service found.\"
fi
'"
