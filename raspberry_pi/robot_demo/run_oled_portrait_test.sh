#!/usr/bin/env bash
set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$TEST_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    printf 'OLED virtual environment not found: %s\n' "$PYTHON" >&2
    exit 1
fi

# User-approved panel 3 portrait test; no robot program or serial connection.
exec "$PYTHON" "$TEST_DIR/test_oled.py" --controller sh1106 --rotate 1 --cycles 5
