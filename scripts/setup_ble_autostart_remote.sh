#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${PI_HOST:?Set PI_HOST to the authorized SSH destination}"
: "${SSH_KEY:?Set SSH_KEY to the existing private key path}"

printf '%s\n' 'This enables CUVO Bluetooth standby at future boots.' \
  'Run only after approving autostart and the fixed dance scope.' \
  'Deploy BLE files first. The old exhibition program must stay disabled.'

SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes "$PI_HOST")
"${SSH[@]}" 'test ! -f ~/.config/autostart/robot-demo.desktop'
"${SSH[@]}" 'test -f ~/capstone-robot-build/ble_control_20261006/robot_demo/ble_credentials.py'
"${SSH[@]}" 'test -x ~/cuvo_oled_test/.venv/bin/python'
"${SSH[@]}" 'mkdir -p ~/.config/systemd/user'
rsync -av --checksum -e "ssh -i $SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=yes" \
  "$PROJECT_ROOT/raspberry_pi/robot_demo/systemd/cuvo-ble.service" \
  "$PI_HOST:.config/systemd/user/"
"${SSH[@]}" 'systemd-analyze --user verify ~/.config/systemd/user/cuvo-ble.service'
"${SSH[@]}" 'loginctl --no-ask-password enable-linger "$(id -un)"'
"${SSH[@]}" 'systemctl --user daemon-reload'
"${SSH[@]}" 'systemctl --user enable cuvo-ble.service'
printf '%s\n' 'Installed and enabled for boot. No current service restart or servo command was issued.'
