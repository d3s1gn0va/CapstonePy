#!/usr/bin/env bash
set -euo pipefail

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"

ssh -i "$SSH_KEY" "$PI_HOST" "bash -lc '
set -euo pipefail

echo \"== Robot process ==\"
pgrep -af \"python.*robot_demo|python.*main.py|run_robot_demo\" || echo \"No matching robot process found.\"

echo
echo \"== Service status ==\"
systemctl --user --no-pager status robot-demo.service 2>/dev/null || systemctl --no-pager status robot-demo.service 2>/dev/null || echo \"robot-demo.service not found.\"

echo
echo \"== Arduino USB Serial candidates ==\"
for pattern in \"/dev/serial/by-id/*\" \"/dev/ttyACM*\" \"/dev/ttyUSB*\"; do
  for candidate in \$pattern; do
    [ -e \"\$candidate\" ] && ls -l \"\$candidate\"
  done
done

echo
echo \"== Audio player ==\"
if command -v pw-play >/dev/null 2>&1; then
  echo \"pw-play: \$(command -v pw-play)\"
else
  echo \"pw-play not found\"
fi

echo
echo \"== Recent logs ==\"
if [ -f \"$REMOTE_ROBOT_DIR/robot_demo.log\" ]; then
  tail -n 30 \"$REMOTE_ROBOT_DIR/robot_demo.log\"
else
  journalctl --user -u robot-demo.service -n 30 --no-pager 2>/dev/null || journalctl -u robot-demo.service -n 30 --no-pager 2>/dev/null || echo \"No robot log source found.\"
fi
'"
