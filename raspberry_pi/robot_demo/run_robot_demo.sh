#!/usr/bin/env bash
set -u

ROBOT_DIR="$HOME/robot_demo"
LOG_FILE="$ROBOT_DIR/robot_demo.log"

# Raspberry Pi 데스크톱, PipeWire 오디오, Arduino USB 인식 대기
sleep 8

cd "$ROBOT_DIR" || exit 1

echo "==================================================" >> "$LOG_FILE"
echo "[Autostart] $(date '+%Y-%m-%d %H:%M:%S') robot demo start" >> "$LOG_FILE"

/usr/bin/python3 "$ROBOT_DIR/main.py" >> "$LOG_FILE" 2>&1
