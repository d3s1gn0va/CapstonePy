#!/usr/bin/env bash
set -euo pipefail

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"
LOCAL_ROBOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/raspberry_pi/robot_demo"

mkdir -p "$LOCAL_ROBOT_DIR"

rsync -av \
  --exclude ".DS_Store" \
  --exclude "._*" \
  --exclude ".env" \
  --exclude ".env.*" \
  --exclude "*.log" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  -e "ssh -i $SSH_KEY" \
  "$PI_HOST:$REMOTE_ROBOT_DIR/" \
  "$LOCAL_ROBOT_DIR/"
