#!/usr/bin/env bash
set -euo pipefail

PI_HOST="hyunwoo@192.168.0.39"
SSH_KEY="$HOME/.ssh/robotpi_ed25519"
REMOTE_ROBOT_DIR="/home/hyunwoo/robot_demo"

cat <<'MESSAGE'
This script prepares a user-level autostart helper on Raspberry Pi OS Desktop.
It waits for the audio session and Arduino USB Serial device before starting the robot demo.
Run it only after you approve enabling autostart behavior on the Raspberry Pi.
MESSAGE

ssh -i "$SSH_KEY" "$PI_HOST" "bash -lc '
set -euo pipefail
mkdir -p ~/.config/autostart ~/.local/bin
cat > ~/.local/bin/start_robot_demo.sh <<\"REMOTE_SCRIPT\"
#!/usr/bin/env bash
set -euo pipefail

ROBOT_DIR=\"$REMOTE_ROBOT_DIR\"
cd \"$REMOTE_ROBOT_DIR\"

for _ in \$(seq 1 20); do
  if command -v pw-play >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

for _ in \$(seq 1 20); do
  if ls /dev/serial/by-id/* /dev/ttyACM* /dev/ttyUSB* >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

python3 main.py >> \"$REMOTE_ROBOT_DIR/robot_demo.log\" 2>&1
REMOTE_SCRIPT
chmod +x ~/.local/bin/start_robot_demo.sh

cat > ~/.config/autostart/robot-demo.desktop <<\"REMOTE_DESKTOP\"
[Desktop Entry]
Type=Application
Name=Robot Demo
Exec=/home/hyunwoo/.local/bin/start_robot_demo.sh
Terminal=false
X-GNOME-Autostart-enabled=true
REMOTE_DESKTOP

echo \"Prepared ~/.local/bin/start_robot_demo.sh and ~/.config/autostart/robot-demo.desktop.\"
echo \"Review these files before relying on autostart during a demonstration.\"
'"
