#!/usr/bin/env bash
set -euo pipefail

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"

ssh -i "$SSH_KEY" "$PI_HOST" "bash -lc '
set -euo pipefail
sudo apt-get update
sudo apt-get install -y \
  git \
  rsync \
  python3 \
  python3-serial \
  python3-gpiozero \
  python3-lgpio \
  alsa-utils \
  pipewire-bin \
  curl
'"
