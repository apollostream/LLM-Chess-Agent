"""Bridge to the existing chess analysis pipeline.

Adds the scripts directory to sys.path so we can import board_utils,
tactical_motifs, and engine_eval directly.
"""

from __future__ import annotations

import sys

import chess

from config import SCRIPTS_DIR

# Add scripts dir to path for imports
_scripts_str = str(SCRIPTS_DIR)
if _scripts_str not in sys.path:
    sys.path.insert(0, _scripts_str)

import board_utils  # noqa: E402
import tactical_motifs  # noqa: E402
from engine_eval import EngineEval  # noqa: E402


def analyze_position(fen: str, use_engine: bool = False,
                     depth: int = 20, lines: int = 3) -> dict:
    """Run full imbalance analysis on a FEN position."""
    board = chess.Board(fen)
    if use_engine:
        with EngineEval() as engine:
            return board_utils.analyze_position(
                board, engine=engine, engine_depth=depth, engine_lines=lines
            )
    return board_utils.analyze_position(board)


def analyze_tactics(fen: str) -> dict:
    """Run tactical motif detection on a FEN position."""
    board = chess.Board(fen)
    return tactical_motifs.analyze_tactics(board)


def evaluate_position(fen: str, depth: int = 20, lines: int = 3) -> dict | None:
    """Run engine evaluation on a FEN position."""
    board = chess.Board(fen)
    with EngineEval() as engine:
        result = engine.evaluate_multipv(board, num_lines=lines, depth=depth)
        single = engine.evaluate_position(board, depth=depth)
    return {
        "eval": single,
        "top_lines": result,
    }


def classify_move(fen: str, move_san: str, depth: int = 20) -> dict | None:
    """Classify a move's quality."""
    board = chess.Board(fen)
    move = board.parse_san(move_san)
    with EngineEval() as engine:
        return engine.classify_move(board, move, depth=depth)
