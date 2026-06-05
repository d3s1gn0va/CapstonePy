#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROBOT_DIR="$PROJECT_ROOT/raspberry_pi/robot_demo"
CACHE_DIR="${TMPDIR:-/tmp}/capstone_robot_pycache"

mkdir -p "$CACHE_DIR"
PYTHONPYCACHEPREFIX="$CACHE_DIR" python3 -m compileall "$ROBOT_DIR"
