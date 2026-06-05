#!/usr/bin/env bash
set -euo pipefail

# DANGER: This script uploads firmware to the Arduino Mega.
# Run only when the user has explicitly said: Arduino 업로드 승인
# Firmware upload can move servos unexpectedly after reset. Keep the mechanism clear.

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ARDUINO_DIR="$PROJECT_ROOT/arduino/servo_controller"
REMOTE_BUILD_DIR="/tmp/capstone_servo_controller"

echo "DANGER: This uploads firmware to Arduino Mega and may cause servo movement."
echo "Continue only after explicit user approval: Arduino 업로드 승인"

ssh -i "$SSH_KEY" "$PI_HOST" "bash -lc '
set -euo pipefail
if systemctl --user list-unit-files robot-demo.service >/dev/null 2>&1; then
  systemctl --user stop robot-demo.service
elif systemctl list-unit-files robot-demo.service >/dev/null 2>&1; then
  sudo systemctl stop robot-demo.service
else
  pkill -f \"python.*robot_demo|python.*main.py\" || true
fi
rm -rf \"$REMOTE_BUILD_DIR\"
mkdir -p \"$REMOTE_BUILD_DIR\"
'"

rsync -av -e "ssh -i $SSH_KEY" "$LOCAL_ARDUINO_DIR/" "$PI_HOST:$REMOTE_BUILD_DIR/"

ssh -i "$SSH_KEY" "$PI_HOST" "bash -lc '
set -euo pipefail
PORT=\"\"
for candidate in /dev/serial/by-id/* /dev/ttyACM* /dev/ttyUSB*; do
  if [ -e \"$candidate\" ]; then
    PORT=\"$candidate\"
    break
  fi
done
if [ -z \"$PORT\" ]; then
  echo \"No Arduino USB Serial device found.\" >&2
  exit 1
fi
arduino-cli compile --fqbn arduino:avr:mega \"$REMOTE_BUILD_DIR\"
arduino-cli upload -p \"$PORT\" --fqbn arduino:avr:mega \"$REMOTE_BUILD_DIR\"
sleep 3
echo \"Upload finished. Check serial response with an approved serial monitor command if needed.\"
echo \"Restart robot program with: scripts/restart_robot.sh\"
'"
