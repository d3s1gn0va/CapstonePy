#!/usr/bin/env bash
set -euo pipefail

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"

cat <<'MESSAGE'
This script installs a narrow sudoers rule on the Raspberry Pi.
It allows the hyunwoo user to run only shutdown without a password:
  /usr/sbin/shutdown -h now

Run this once before relying on the physical power-off button.
MESSAGE

ssh -tt -i "$SSH_KEY" "$PI_HOST" "bash -lc '
set -euo pipefail
TMP_FILE=\$(mktemp)
trap \"rm -f \\\"\$TMP_FILE\\\"\" EXIT
cat > \"\$TMP_FILE\" <<\"SUDOERS\"
hyunwoo ALL=(root) NOPASSWD: /usr/sbin/shutdown -h now
SUDOERS
sudo visudo -cf \"\$TMP_FILE\"
sudo install -m 0440 \"\$TMP_FILE\" /etc/sudoers.d/010-robot-shutdown
echo \"Installed /etc/sudoers.d/010-robot-shutdown\"
'"
