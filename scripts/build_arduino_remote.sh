#!/usr/bin/env bash
set -euo pipefail

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"
REMOTE_BUILD_DIR="/home/hyunwoo/capstone-robot-build/servo_controller"
ARDUINO_FQBN="arduino:avr:mega"
ARDUINO_CLI="/home/hyunwoo/.local/bin/arduino-cli"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ARDUINO_DIR="$PROJECT_ROOT/arduino/servo_controller"

test -f "$LOCAL_ARDUINO_DIR/servo_controller.ino"

ssh -i "$SSH_KEY" "$PI_HOST" "mkdir -p '$REMOTE_BUILD_DIR'"
rsync -av --delete \
  --exclude ".DS_Store" \
  --exclude "._*" \
  -e "ssh -i $SSH_KEY" \
  "$LOCAL_ARDUINO_DIR/" \
  "$PI_HOST:$REMOTE_BUILD_DIR/"

ssh -i "$SSH_KEY" "$PI_HOST" "'$ARDUINO_CLI' compile --fqbn '$ARDUINO_FQBN' '$REMOTE_BUILD_DIR'"
