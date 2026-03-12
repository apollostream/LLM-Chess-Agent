#!/usr/bin/env bash
# CLI wrapper for board_utils.py — resolves the project venv automatically.
#
# Usage:
#   parse_position.sh <FEN | PGN_FILE | MOVES> [--format text|json] [--move N|Nb]
#
# Examples:
#   parse_position.sh "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
#   parse_position.sh game.pgn --format text
#   parse_position.sh game.pgn --move 15          # after White's 15th
#   parse_position.sh game.pgn --move 15b         # after Black's 15th
#   parse_position.sh "1. e4 e5 2. Nf3 Nc6"
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "Error: Python venv not found at $VENV_PYTHON" >&2
    echo "Run install_deps.sh first." >&2
    exit 1
fi

exec "$VENV_PYTHON" "$SCRIPT_DIR/board_utils.py" "$@"
