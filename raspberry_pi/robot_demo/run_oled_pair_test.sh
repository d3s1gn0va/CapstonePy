#!/usr/bin/env bash
set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Confirmed installed panel mapping: CE1=viewer-left, CE0=viewer-right.
exec "$TEST_DIR/.venv/bin/python" "$TEST_DIR/test_oled_pair.py" --swap-displays "$@"
