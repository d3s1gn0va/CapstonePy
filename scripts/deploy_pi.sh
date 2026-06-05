#!/usr/bin/env bash
set -euo pipefail

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ROBOT_DIR="$PROJECT_ROOT/raspberry_pi/robot_demo"

"$PROJECT_ROOT/scripts/check_python.sh"

rsync -av \
  --exclude ".env" \
  --exclude "*.log" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  -e "ssh -i $SSH_KEY" \
  "$LOCAL_ROBOT_DIR/" \
  "$PI_HOST:$REMOTE_ROBOT_DIR/"

ssh -i "$SSH_KEY" "$PI_HOST" "find '$REMOTE_ROBOT_DIR' -maxdepth 2 -type f | sort | sed -n '1,80p'"
