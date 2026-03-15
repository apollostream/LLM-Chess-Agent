"""Tests for cache-aware critical moment detection."""

import sys
from pathlib import Path

import pytest

# Add scripts to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "chess-imbalances" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from game_narrative import detect_critical_moments_from_cache, CriticalMoment


# A simple 3-move game: 1. e4 e5 2. Qh5 (threatening scholar's mate)
SIMPLE_PGN = '[Event "Test"]\n[Result "*"]\n\n1. e4 e5 2. Qh5 Nc6 *'

# Positions from this game:
FENS = [
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",       # start
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",      # after 1. e4
    "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",    # after 1...e5
    "rnbqkbnr/pppp1ppp/8/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR b KQkq - 1 2",   # after 2. Qh5
    "r1bqkbnr/pppp1ppp/2n5/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 2 3", # after 2...Nc6
]


def _build_eval_cache(scores: list[int]) -> dict[str, dict]:
    """Build an eval cache from a list of centipawn scores, one per FEN."""
    cache = {}
    for fen, cp in zip(FENS, scores):
        cache[fen] = {
            "eval": {"score_cp": cp, "best_move": "e4", "best_move_uci": "e2e4"},
            "top_lines": [{"best_move": "e4", "score_cp": cp}],
        }
    return cache


class TestMomentsFromCache:
    def test_basic_detection(self):
        """Given pre-computed evals with a big swing, detects moments."""
        # Scores: start=0, after e4=+30, after e5=+25, after Qh5=+200, after Nc6=+50
        # The swing at Qh5 (+25 → +200 = +175cp) and at Nc6 (+200 → +50 = -150cp)
        # should both be detected with threshold_cp=50
        cache = _build_eval_cache([0, 30, 25, 200, 50])
        moments = detect_critical_moments_from_cache(
            SIMPLE_PGN, cache, threshold_cp=50, decay_scale_cp=None,
        )
        assert len(moments) >= 1
        assert all(isinstance(m, CriticalMoment) for m in moments)

        # Check the big swing is detected
        deltas = [abs(m.delta_cp) for m in moments]
        assert max(deltas) >= 100

    def test_decay_logic(self):
        """Decay logic suppresses swings in lopsided positions."""
        # Scores: 0, +30, +800, +850, +900
        # After e5 the position is already +800. The swing +800→+850 = 50cp
        # With decay at scale=750, effective_threshold ≈ 50 / exp(-800/750) ≈ 145cp
        # So the 50cp swing should NOT trigger.
        cache = _build_eval_cache([0, 30, 800, 850, 900])
        moments = detect_critical_moments_from_cache(
            SIMPLE_PGN, cache, threshold_cp=50, decay_scale_cp=750,
        )
        # Only the initial big jump (30→800) should be flagged
        assert all(abs(m.delta_cp) > 100 for m in moments)

    def test_accepts_pgn_text(self):
        """Accepts PGN text directly, not a file path."""
        cache = _build_eval_cache([0, 30, 25, 200, 50])
        # Should not raise — the function takes text, not Path
        moments = detect_critical_moments_from_cache(
            SIMPLE_PGN, cache, threshold_cp=50,
        )
        assert isinstance(moments, list)

    def test_empty_cache(self):
        """Returns empty list if cache has no matching FENs."""
        moments = detect_critical_moments_from_cache(
            SIMPLE_PGN, {}, threshold_cp=50,
        )
        assert moments == []

    def test_moment_fields(self):
        """Each moment has all required fields populated."""
        cache = _build_eval_cache([0, 30, 25, 200, 50])
        moments = detect_critical_moments_from_cache(
            SIMPLE_PGN, cache, threshold_cp=50, decay_scale_cp=None,
        )
        for m in moments:
            assert m.move_number >= 1
            assert m.side in ("white", "black")
            assert m.san != ""
            assert m.fen_before != ""
            assert m.fen_after != ""
            assert m.classification in ("best", "excellent", "good", "inaccuracy", "mistake", "blunder")
