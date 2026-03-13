#!/usr/bin/env python3
"""Stockfish engine integration for chess position analysis.

Provides evaluation, multi-PV analysis, and move classification via python-chess's
UCI engine protocol. Gracefully degrades when Stockfish is not available.

Usage:
    from engine_eval import EngineEval

    with EngineEval() as engine:
        result = engine.evaluate_position(board)
        lines = engine.evaluate_multipv(board, num_lines=3)
        classification = engine.classify_move(board, move)
"""

import shutil
from pathlib import Path

import chess
import chess.engine


# ── Stockfish discovery ──────────────────────────────────────────────────────

STOCKFISH_SEARCH_PATHS = [
    "stockfish",                    # on PATH
    "/usr/games/stockfish",         # Ubuntu/Debian apt
    "/usr/local/bin/stockfish",     # manual install
    "/usr/bin/stockfish",           # some distros
    "/snap/bin/stockfish",          # snap
    "/opt/homebrew/bin/stockfish",  # macOS Homebrew
]


def find_stockfish() -> str | None:
    """Auto-discover Stockfish binary. Returns path or None."""
    for path in STOCKFISH_SEARCH_PATHS:
        resolved = shutil.which(path)
        if resolved:
            return resolved
    return None


# ── Move classification thresholds ───────────────────────────────────────────

# Centipawn loss thresholds for move classification
# Based on common chess analysis standards (similar to chess.com/lichess)
MOVE_CLASSIFICATIONS = [
    (0, "best"),         # 0 cp loss — the engine's top choice
    (10, "excellent"),   # ≤10 cp loss
    (25, "good"),        # ≤25 cp loss
    (50, "inaccuracy"),  # ≤50 cp loss
    (100, "mistake"),    # ≤100 cp loss
    (200, "blunder"),    # ≤200 cp loss
    (float("inf"), "blunder"),  # >200 cp loss
]


def _classify_cp_loss(cp_loss: int) -> str:
    """Classify a move based on centipawn loss."""
    for threshold, label in MOVE_CLASSIFICATIONS:
        if cp_loss <= threshold:
            return label
    return "blunder"


def _score_to_cp(score: chess.engine.PovScore, turn: chess.Color) -> int | None:
    """Convert a PovScore to centipawns from the given side's perspective.

    Returns None for mate scores (handled separately).
    """
    relative = score.pov(turn)
    cp = relative.score()
    return cp  # None if mate


def _score_display(score: chess.engine.PovScore) -> str:
    """Human-readable score string from White's perspective."""
    white_score = score.white()
    mate = white_score.mate()
    if mate is not None:
        if mate > 0:
            return f"M{mate}"
        elif mate < 0:
            return f"-M{abs(mate)}"
        else:
            return "M0"
    cp = white_score.score()
    if cp is None:
        return "?"
    sign = "+" if cp >= 0 else ""
    return f"{sign}{cp / 100:.2f}"


# ── Engine wrapper ───────────────────────────────────────────────────────────

class EngineEval:
    """Context-managed Stockfish engine wrapper.

    Usage:
        with EngineEval() as engine:
            result = engine.evaluate_position(board)

    Or manually:
        engine = EngineEval()
        engine.open()
        ...
        engine.close()

    If Stockfish is not found, open() sets self.available = False and all
    methods return None gracefully.
    """

    def __init__(self, path: str | None = None, threads: int = 1, hash_mb: int = 64):
        self.path = path or find_stockfish()
        self.threads = threads
        self.hash_mb = hash_mb
        self._engine: chess.engine.SimpleEngine | None = None
        self.available = False

    def open(self) -> "EngineEval":
        if self.path is None:
            self.available = False
            return self
        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
            self._engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
            self.available = True
        except (chess.engine.EngineTerminatedError, FileNotFoundError, OSError):
            self._engine = None
            self.available = False
        return self

    def close(self):
        if self._engine:
            try:
                self._engine.quit()
            except chess.engine.EngineTerminatedError:
                pass
            self._engine = None
            self.available = False

    def __enter__(self) -> "EngineEval":
        return self.open()

    def __exit__(self, *args):
        self.close()

    def evaluate_position(self, board: chess.Board, depth: int = 20) -> dict | None:
        """Evaluate a position, returning eval, best move, PV, and WDL.

        Returns dict with keys:
            score_cp: int | None (centipawns from White's perspective)
            score_display: str (e.g. "+0.33", "-1.50", "M3")
            mate_in: int | None (moves to mate, negative = being mated)
            best_move: str (SAN)
            best_move_uci: str (UCI)
            pv: list[str] (principal variation in SAN, up to 10 moves)
            pv_uci: list[str] (principal variation in UCI)
            wdl: dict | None ({"win": int, "draw": int, "loss": int} per mille from White's perspective)
            depth: int (search depth reached)

        Returns None if engine is unavailable.
        """
        if not self.available or not self._engine:
            return None

        info = self._engine.analyse(board, chess.engine.Limit(depth=depth))
        score = info["score"]
        pv_moves = info.get("pv", [])

        # Build SAN PV by replaying moves
        pv_san = []
        pv_board = board.copy()
        for move in pv_moves[:10]:
            try:
                pv_san.append(pv_board.san(move))
                pv_board.push(move)
            except (ValueError, AssertionError):
                break

        white_score = score.white()
        mate = white_score.mate()

        # WDL if available
        wdl = None
        try:
            wdl_obj = score.white().wdl()
            wdl = {"win": wdl_obj.wins, "draw": wdl_obj.draws, "loss": wdl_obj.losses}
        except Exception:
            pass

        # Best move
        best_move_san = None
        best_move_uci = None
        if pv_moves:
            best_move_uci = pv_moves[0].uci()
            try:
                best_move_san = board.san(pv_moves[0])
            except (ValueError, AssertionError):
                best_move_san = best_move_uci

        return {
            "score_cp": white_score.score(),
            "score_display": _score_display(score),
            "mate_in": mate,
            "best_move": best_move_san,
            "best_move_uci": best_move_uci,
            "pv": pv_san,
            "pv_uci": [m.uci() for m in pv_moves[:10]],
            "wdl": wdl,
            "depth": info.get("depth", depth),
        }

    def evaluate_multipv(self, board: chess.Board, num_lines: int = 3,
                         depth: int = 20) -> list[dict] | None:
        """Return top N lines with evaluations.

        Each line is a dict with the same structure as evaluate_position().
        Returns None if engine is unavailable.
        """
        if not self.available or not self._engine:
            return None

        results = self._engine.analyse(board, chess.engine.Limit(depth=depth),
                                       multipv=num_lines)
        if not isinstance(results, list):
            results = [results]

        lines = []
        for info in results:
            score = info["score"]
            pv_moves = info.get("pv", [])

            pv_san = []
            pv_board = board.copy()
            for move in pv_moves[:10]:
                try:
                    pv_san.append(pv_board.san(move))
                    pv_board.push(move)
                except (ValueError, AssertionError):
                    break

            white_score = score.white()
            mate = white_score.mate()

            wdl = None
            try:
                wdl_obj = score.white().wdl()
                wdl = {"win": wdl_obj.wins, "draw": wdl_obj.draws, "loss": wdl_obj.losses}
            except Exception:
                pass

            best_move_san = None
            best_move_uci = None
            if pv_moves:
                best_move_uci = pv_moves[0].uci()
                try:
                    best_move_san = board.san(pv_moves[0])
                except (ValueError, AssertionError):
                    best_move_san = best_move_uci

            lines.append({
                "score_cp": white_score.score(),
                "score_display": _score_display(score),
                "mate_in": mate,
                "best_move": best_move_san,
                "best_move_uci": best_move_uci,
                "pv": pv_san,
                "pv_uci": [m.uci() for m in pv_moves[:10]],
                "wdl": wdl,
                "depth": info.get("depth", depth),
            })

        return lines

    def classify_move(self, board: chess.Board, move: chess.Move,
                      depth: int = 20) -> dict | None:
        """Classify a move as best/excellent/good/inaccuracy/mistake/blunder.

        Uses multi-PV analysis to compare the played move against alternatives
        in a single engine call, avoiding non-determinism from separate searches.

        Returns dict with keys:
            move: str (SAN)
            classification: str
            cp_loss: int (centipawn loss vs best move)
            eval_before: str (display score before)
            eval_after: str (display score after the move)
            best_move: str (SAN of best move)
            best_eval: str (display score of best move)
            is_best: bool

        Returns None if engine is unavailable.
        """
        if not self.available or not self._engine:
            return None

        turn = board.turn

        # Use multi-PV to get a range of moves and their evals in one call.
        # Request enough lines to likely include the played move.
        multi_results = self._engine.analyse(board, chess.engine.Limit(depth=depth),
                                             multipv=min(len(list(board.legal_moves)), 50))
        if not isinstance(multi_results, list):
            multi_results = [multi_results]

        # Find best eval and the played move's eval
        best_info = multi_results[0] if multi_results else None
        played_info = None
        for info in multi_results:
            pv = info.get("pv", [])
            if pv and pv[0] == move:
                played_info = info
                break

        if best_info is None:
            return None

        best_score = best_info["score"]
        best_pv = best_info.get("pv", [])
        best_move_obj = best_pv[0] if best_pv else None
        best_cp = _score_to_cp(best_score, turn)

        is_best = (best_move_obj == move) if best_move_obj else False

        # If we found the played move in multi-PV, use its eval directly
        if played_info is not None:
            played_score = played_info["score"]
            played_cp = _score_to_cp(played_score, turn)
        else:
            # Fallback: evaluate position after the move (rare — only if move
            # wasn't in the top 50 multi-PV lines)
            board_after = board.copy()
            board_after.push(move)
            after_info = self._engine.analyse(board_after, chess.engine.Limit(depth=depth))
            played_score = after_info["score"]
            played_cp = _score_to_cp(played_score, turn)

        # Calculate CP loss
        if best_cp is not None and played_cp is not None:
            cp_loss = max(0, best_cp - played_cp)
        elif best_cp is not None and played_cp is None:
            played_mate = played_score.pov(turn).mate()
            if played_mate is not None and played_mate > 0:
                cp_loss = 0  # Found a mate — can't be bad
            else:
                cp_loss = 999  # Getting mated
        elif best_cp is None and played_cp is not None:
            best_mate = best_score.pov(turn).mate()
            if best_mate is not None and best_mate > 0:
                cp_loss = 300  # Missed a forced mate — always a blunder
            else:
                cp_loss = 0
        else:
            # Both are mates
            cp_loss = 0 if is_best else 50

        try:
            move_san = board.san(move)
        except (ValueError, AssertionError):
            move_san = move.uci()

        best_move_san = None
        if best_move_obj:
            try:
                best_move_san = board.san(best_move_obj)
            except (ValueError, AssertionError):
                best_move_san = best_move_obj.uci()

        return {
            "move": move_san,
            "classification": "best" if is_best else _classify_cp_loss(cp_loss),
            "cp_loss": cp_loss,
            "eval_before": _score_display(best_score),
            "eval_after": _score_display(played_score),
            "best_move": best_move_san,
            "best_eval": _score_display(best_score),
            "is_best": is_best,
        }
