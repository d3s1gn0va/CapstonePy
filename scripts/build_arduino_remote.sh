#!/usr/bin/env bash
set -euo pipefail

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ARDUINO_DIR="$PROJECT_ROOT/arduino/servo_controller"
REMOTE_BUILD_DIR="/tmp/capstone_servo_controller"

ssh -i "$SSH_KEY" "$PI_HOST" "rm -rf '$REMOTE_BUILD_DIR' && mkdir -p '$REMOTE_BUILD_DIR'"
rsync -av -e "ssh -i $SSH_KEY" "$LOCAL_ARDUINO_DIR/" "$PI_HOST:$REMOTE_BUILD_DIR/"
ssh -i "$SSH_KEY" "$PI_HOST" "arduino-cli compile --fqbn arduino:avr:mega '$REMOTE_BUILD_DIR'"
