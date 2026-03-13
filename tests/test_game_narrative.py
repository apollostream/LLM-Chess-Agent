"""Tests for game narrative pipeline — TDD Red phase.

Tests critical moment detection, GameNarrative models, and rendering.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from pydantic import ValidationError

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude" / "skills" / "chess-imbalances" / "scripts"))

from game_narrative import (
    CriticalMoment,
    GameNarrative,
    ArcType,
    detect_critical_moments,
    render_game_story,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

SAMPLE_PGN = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. d4 exd4 5. Nxd4 Nf6 1-0"

def make_critical_moment(**overrides):
    defaults = {
        "move_number": 5,
        "side": "white",
        "san": "Nbd2",
        "fen_before": "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 5",
        "fen_after": "rnbqkb1r/pppp1ppp/5n2/4p3/2B1P3/5N2/PPPPNPPP/R1BQK2R b KQkq - 1 5",
        "eval_before_cp": 66,
        "eval_after_cp": -28,
        "delta_cp": -94,
        "classification": "mistake",
        "engine_best_move": "Nxd4",
        "key_lesson": None,
    }
    defaults.update(overrides)
    return CriticalMoment(**defaults)


def make_game_narrative(**overrides):
    defaults = {
        "game_metadata": {
            "white": "Jade-BOT",
            "black": "pjqweewrq",
            "date": "2026.03.11",
            "result": "0-1",
            "eco": "C55",
            "opening": "Italian Game",
        },
        "critical_moments": [
            make_critical_moment().model_dump(),
            make_critical_moment(
                move_number=7, san="g3", delta_cp=-107,
                classification="blunder",
                eval_before_cp=-45, eval_after_cp=-152,
            ).model_dump(),
            make_critical_moment(
                move_number=11, side="white", san="Be2", delta_cp=-113,
                classification="blunder",
                eval_before_cp=-3, eval_after_cp=-116,
            ).model_dump(),
        ],
        "arc_type": "gradual_collapse",
        "game_story": (
            "White won the structural battle with 10.Nxb6 but lost the war. "
            "Three bishop moves consumed the exact tempo needed for castling, "
            "and by move 14 the accumulated cost was insurmountable. The game "
            "illustrates how small, reasonable-looking decisions compound into "
            "a losing position when they all delay the same critical task: king safety."
        ),
        "key_lessons": [
            "Follow through on piece commitments — a knight journey that doesn't capture wastes tempo",
            "Complete fianchetto structures (g3 must lead to Bg2) — half-finished plans create weaknesses for nothing",
            "Castle before improving pieces — in open positions, king safety trumps everything",
        ],
        "turning_point_move": 5,
        "turning_point_side": "white",
    }
    defaults.update(overrides)
    return GameNarrative(**defaults)


# ── TestCriticalMoment ──────────────────────────────────────────────────────

class TestCriticalMoment:
    def test_valid(self):
        cm = make_critical_moment()
        assert cm.move_number == 5
        assert cm.side == "white"
        assert cm.delta_cp == -94

    def test_classification_values(self):
        for cls in ["best", "excellent", "good", "inaccuracy", "mistake", "blunder"]:
            cm = make_critical_moment(classification=cls)
            assert cm.classification == cls

    def test_optional_key_lesson(self):
        cm = make_critical_moment(key_lesson="Castle early in open positions")
        assert cm.key_lesson == "Castle early in open positions"

    def test_side_must_be_white_or_black(self):
        with pytest.raises(ValidationError):
            make_critical_moment(side="red")


# ── TestGameNarrative ──────────────────────────────────────────────────────

class TestGameNarrative:
    def test_valid(self):
        gn = make_game_narrative()
        assert gn.arc_type == ArcType.gradual_collapse
        assert len(gn.critical_moments) == 3
        assert len(gn.key_lessons) == 3

    def test_game_story_min_length(self):
        with pytest.raises(ValidationError, match="game_story"):
            make_game_narrative(game_story="Too short.")

    def test_key_lessons_required(self):
        with pytest.raises(ValidationError, match="key_lessons"):
            make_game_narrative(key_lessons=[])

    def test_critical_moments_required(self):
        with pytest.raises(ValidationError, match="critical_moments"):
            make_game_narrative(critical_moments=[])

    def test_arc_types(self):
        for arc in ["gradual_collapse", "single_blunder", "back_and_forth",
                     "missed_opportunity", "steady_conversion"]:
            gn = make_game_narrative(arc_type=arc)
            assert gn.arc_type.value == arc

    def test_turning_point(self):
        gn = make_game_narrative()
        assert gn.turning_point_move == 5
        assert gn.turning_point_side == "white"

    def test_game_metadata(self):
        gn = make_game_narrative()
        assert gn.game_metadata["white"] == "Jade-BOT"
        assert gn.game_metadata["result"] == "0-1"


# ── TestDetectCriticalMoments ──────────────────────────────────────────────

class TestDetectCriticalMoments:
    def test_returns_list(self, tmp_path):
        """detect_critical_moments returns a list of CriticalMoment."""
        pgn_path = tmp_path / "test.pgn"
        pgn_path.write_text(
            '[Event "Test"]\n[Result "1-0"]\n\n'
            "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 1-0\n"
        )
        result = detect_critical_moments(pgn_path, depth=8)
        assert isinstance(result, list)
        for cm in result:
            assert isinstance(cm, CriticalMoment)

    def test_threshold_filtering(self, tmp_path):
        """Higher threshold should return fewer (or equal) moments."""
        pgn_path = tmp_path / "test.pgn"
        pgn_path.write_text(
            '[Event "Test"]\n[Result "1-0"]\n\n'
            "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 1-0\n"
        )
        low = detect_critical_moments(pgn_path, depth=8, threshold_cp=10)
        high = detect_critical_moments(pgn_path, depth=8, threshold_cp=200)
        assert len(high) <= len(low)

    def test_each_moment_has_required_fields(self, tmp_path):
        pgn_path = tmp_path / "test.pgn"
        pgn_path.write_text(
            '[Event "Test"]\n[Result "1-0"]\n\n'
            "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 1-0\n"
        )
        moments = detect_critical_moments(pgn_path, depth=8, threshold_cp=0)
        for cm in moments:
            assert cm.fen_before is not None
            assert cm.fen_after is not None
            assert cm.san is not None
            assert cm.side in ("white", "black")

    def test_real_game_finds_blunders(self):
        """The Jade-BOT game should have detectable critical moments."""
        pgn_path = Path.home() / "Documents/Chess/Jade-BOT_vs_pjqweewrq_2026.03.11.pgn"
        if not pgn_path.exists():
            pytest.skip("Jade-BOT PGN not available")
        moments = detect_critical_moments(pgn_path, depth=12, threshold_cp=80)
        # We know this game has several blunders
        assert len(moments) >= 3
        # The first big swing should be around move 5 (Nbd2)
        moves = [cm.move_number for cm in moments]
        assert any(m <= 7 for m in moves), f"Expected early blunder, got moves: {moves}"


# ── TestRenderGameStory ────────────────────────────────────────────────────

class TestRenderGameStory:
    def test_render_has_title(self):
        gn = make_game_narrative()
        md = render_game_story(gn)
        assert "Game Story" in md or "Game Narrative" in md

    def test_render_includes_players(self):
        gn = make_game_narrative()
        md = render_game_story(gn)
        assert "Jade-BOT" in md
        assert "pjqweewrq" in md

    def test_render_includes_story(self):
        gn = make_game_narrative()
        md = render_game_story(gn)
        assert "structural battle" in md

    def test_render_includes_critical_moments(self):
        gn = make_game_narrative()
        md = render_game_story(gn)
        assert "Nbd2" in md or "g3" in md or "Be2" in md

    def test_render_includes_lessons(self):
        gn = make_game_narrative()
        md = render_game_story(gn)
        assert "fianchetto" in md.lower() or "castle" in md.lower()

    def test_render_includes_turning_point(self):
        gn = make_game_narrative()
        md = render_game_story(gn)
        assert "turning point" in md.lower() or "tipping point" in md.lower()

    def test_render_includes_eval_data(self):
        gn = make_game_narrative()
        md = render_game_story(gn)
        # Should show eval deltas for critical moments
        assert "-0.94" in md or "-94" in md or "mistake" in md.lower()

    def test_render_includes_arc_type(self):
        gn = make_game_narrative()
        md = render_game_story(gn)
        assert "gradual" in md.lower() or "collapse" in md.lower()

    def test_render_is_reasonable_length(self):
        gn = make_game_narrative()
        md = render_game_story(gn)
        # Should be substantial but not enormous
        assert 200 < len(md) < 10000

    def test_render_with_output_path(self, tmp_path):
        gn = make_game_narrative()
        output = tmp_path / "story.md"
        md = render_game_story(gn, output_path=output)
        assert output.exists()
        assert output.read_text() == md
