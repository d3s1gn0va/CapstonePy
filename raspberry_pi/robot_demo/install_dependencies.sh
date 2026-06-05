#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y \
  python3 \
  python3-serial \
  python3-gpiozero \
  python3-lgpio \
  alsa-utils

echo
echo "설치 완료"
echo "다음 단계:"
echo "  cd ~/robot_demo"
echo "  python3 test_audio.py"
