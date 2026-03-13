#!/usr/bin/env bash
# One-time dependency installer for chess-imbalances skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VENV="$PROJECT_ROOT/.venv"

if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment at $VENV"
    python3 -m venv "$VENV"
fi

echo "Installing dependencies into $VENV"
"$VENV/bin/pip" install -r "$PROJECT_ROOT/requirements.txt"
echo "Done."
