#!/usr/bin/env bash
set -euo pipefail

# DANGER: This script uploads firmware to the Arduino Mega.
# Run only after the user explicitly says: Arduino 업로드 승인
# Firmware upload resets the Arduino and may cause servo movement.

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"
REMOTE_BUILD_DIR="/home/hyunwoo/capstone-robot-build/servo_controller"
ARDUINO_FQBN="arduino:avr:mega"
ARDUINO_CLI="/home/hyunwoo/.local/bin/arduino-cli"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ARDUINO_DIR="$PROJECT_ROOT/arduino/servo_controller"

cat <<'WARNING'
DANGER: Arduino Mega firmware upload can reset the board and may move servos.
Keep the robot mechanism clear and powered safely.

This script must be run only after explicit user approval:
Arduino 업로드 승인
WARNING

printf "Type the exact approval phrase to continue: "
IFS= read -r APPROVAL
if [ "$APPROVAL" != "Arduino 업로드 승인" ]; then
  echo "Aborted: approval phrase did not match."
  exit 1
fi

test -f "$LOCAL_ARDUINO_DIR/servo_controller.ino"

ssh -i "$SSH_KEY" "$PI_HOST" "mkdir -p '$REMOTE_BUILD_DIR'"
rsync -av --delete \
  --exclude ".DS_Store" \
  --exclude "._*" \
  -e "ssh -i $SSH_KEY" \
  "$LOCAL_ARDUINO_DIR/" \
  "$PI_HOST:$REMOTE_BUILD_DIR/"

ssh -i "$SSH_KEY" "$PI_HOST" \
  "REMOTE_ROBOT_DIR='$REMOTE_ROBOT_DIR' REMOTE_BUILD_DIR='$REMOTE_BUILD_DIR' ARDUINO_FQBN='$ARDUINO_FQBN' ARDUINO_CLI='$ARDUINO_CLI' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

find_arduino_port() {
  local candidate
  for candidate in /dev/serial/by-id/* /dev/ttyACM* /dev/ttyUSB*; do
    if [ -e "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

echo "Stopping robot program before firmware upload..."
if systemctl --user list-unit-files robot-demo.service >/dev/null 2>&1; then
  systemctl --user stop robot-demo.service || true
elif systemctl list-unit-files robot-demo.service >/dev/null 2>&1; then
  sudo systemctl stop robot-demo.service || true
else
  pkill -f "python.*robot_demo|python.*main.py|run_robot_demo" || true
fi

PORT="$(find_arduino_port || true)"
if [ -z "$PORT" ]; then
  echo "No Arduino USB Serial device found." >&2
  exit 1
fi

echo "Using Arduino port: $PORT"
"$ARDUINO_CLI" compile --fqbn "$ARDUINO_FQBN" "$REMOTE_BUILD_DIR"
"$ARDUINO_CLI" upload -p "$PORT" --fqbn "$ARDUINO_FQBN" "$REMOTE_BUILD_DIR"

echo "Waiting for Arduino reset..."
sleep 3

echo "Checking Arduino PING response..."
python3 - "$PORT" <<'PY'
import sys
import time

import serial

port = sys.argv[1]
with serial.Serial(port, 115200, timeout=1.5) as ser:
    time.sleep(2.0)
    ser.reset_input_buffer()
    ser.write(b"PING\n")
    ser.flush()
    deadline = time.time() + 5.0
    lines = []
    while time.time() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        text = raw.decode("utf-8", errors="replace").strip()
        lines.append(text)
        print(text)
        if text == "ACK,PING":
            sys.exit(0)

print("Arduino did not return ACK,PING.", file=sys.stderr)
if lines:
    print("Received lines: " + " | ".join(lines), file=sys.stderr)
sys.exit(1)
PY

echo "Upload and PING check finished."
echo "Restart the robot program after a final safety check:"
echo "  scripts/restart_robot.sh"
REMOTE_SCRIPT
