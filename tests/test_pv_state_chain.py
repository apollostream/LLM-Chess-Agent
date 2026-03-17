"""Tests for pv_state_chain — replay PV moves and build feature tables."""

import json
import sys
from pathlib import Path

import chess
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "chess-imbalances" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from imbalance_vectorizer import FEATURE_NAMES
from imbalance_vectorizer import STM_FEATURE_NAMES
from pv_state_chain import (
    replay_pv,
    build_game_transition_table,
    build_game_stm_table,
    build_pv_comparison_table,
)


GAME_CACHE_DIR = Path(__file__).resolve().parent.parent / "analysis" / "game_cache"


class TestReplayPV:
    """Replay a PV from a known position and collect structural snapshots."""

    def test_replay_starting_position(self):
        """Replay 1.e4 e5 2.Nf3 from starting position."""
        board = chess.Board()
        pv_uci = ["e2e4", "e7e5", "g1f3"]
        rows = replay_pv(board, pv_uci)

        # 4 rows: root + 3 moves
        assert len(rows) == 4

    def test_root_row_has_no_move(self):
        board = chess.Board()
        pv_uci = ["e2e4"]
        rows = replay_pv(board, pv_uci)
        assert rows[0]["move_san"] is None
        assert rows[0]["ply"] == 0

    def test_subsequent_rows_have_moves(self):
        board = chess.Board()
        pv_uci = ["e2e4", "e7e5"]
        rows = replay_pv(board, pv_uci)
        assert rows[1]["move_san"] == "e4"
        assert rows[1]["ply"] == 1
        assert rows[2]["move_san"] == "e5"
        assert rows[2]["ply"] == 2

    def test_features_present_in_each_row(self):
        board = chess.Board()
        pv_uci = ["e2e4"]
        rows = replay_pv(board, pv_uci)
        for row in rows:
            for name in FEATURE_NAMES:
                assert name in row, f"Missing feature: {name}"

    def test_deltas_present_from_ply_1(self):
        board = chess.Board()
        pv_uci = ["e2e4"]
        rows = replay_pv(board, pv_uci)
        # Row 0 (root) should have no deltas
        assert "d_material_balance" not in rows[0]
        # Row 1 should have deltas
        assert "d_material_balance" in rows[1]

    def test_fen_changes_along_pv(self):
        board = chess.Board()
        pv_uci = ["e2e4", "e7e5"]
        rows = replay_pv(board, pv_uci)
        assert rows[0]["fen"] != rows[1]["fen"]
        assert rows[1]["fen"] != rows[2]["fen"]


class TestBuildGameTransitionTable:
    """Build a table from actual game positions with real eval deltas."""

    @pytest.fixture
    def sample_cache(self):
        """Load a real game cache if available, else skip."""
        cache_files = list(GAME_CACHE_DIR.glob("*.json"))
        if not cache_files:
            pytest.skip("No game cache files available")
        with open(cache_files[0]) as f:
            return json.load(f)

    def test_table_has_rows(self, sample_cache):
        table = build_game_transition_table(sample_cache)
        assert len(table) > 0

    def test_columns_include_eval(self, sample_cache):
        table = build_game_transition_table(sample_cache)
        row = table[0]
        assert "eval_cp" in row

    def test_deltas_from_row_1(self, sample_cache):
        table = build_game_transition_table(sample_cache)
        if len(table) > 1:
            assert "d_material_balance" in table[1]
            assert "d_eval_cp" in table[1]

    def test_game_id_in_rows(self, sample_cache):
        table = build_game_transition_table(sample_cache)
        assert "game_id" in table[0]


class TestBuildGameSTMTable:
    """STM-relative game transition table — color-agnostic features."""

    @pytest.fixture
    def sample_cache(self):
        cache_files = list(GAME_CACHE_DIR.glob("*.json"))
        if not cache_files:
            pytest.skip("No game cache files available")
        with open(cache_files[0]) as f:
            return json.load(f)

    def test_table_has_rows(self, sample_cache):
        table = build_game_stm_table(sample_cache, max_positions=10)
        assert len(table) > 0

    def test_stm_features_present(self, sample_cache):
        table = build_game_stm_table(sample_cache, max_positions=5)
        row = table[0]
        for name in STM_FEATURE_NAMES:
            assert name in row, f"Missing STM feature: {name}"

    def test_eval_stm_present(self, sample_cache):
        table = build_game_stm_table(sample_cache, max_positions=5)
        assert "eval_stm" in table[0]

    def test_deltas_use_stm_names(self, sample_cache):
        table = build_game_stm_table(sample_cache, max_positions=5)
        if len(table) > 1:
            # Delta columns should use STM names, not white/black
            assert "d_initiative_score_stm" in table[1]
            assert "d_initiative_score_white" not in table[1]

    def test_no_side_to_move_column(self, sample_cache):
        """STM representation shouldn't have side_to_move — it's implicit."""
        table = build_game_stm_table(sample_cache, max_positions=5)
        assert "side_to_move" not in table[0]


class TestBuildPVComparisonTable:
    """Compare PV1 vs PVN structural differences at each position."""

    @pytest.fixture
    def sample_cache(self):
        cache_files = list(GAME_CACHE_DIR.glob("*.json"))
        if not cache_files:
            pytest.skip("No game cache files available")
        with open(cache_files[0]) as f:
            return json.load(f)

    def test_table_has_rows(self, sample_cache):
        table = build_pv_comparison_table(sample_cache, pv_depth=2)
        assert len(table) > 0

    def test_columns_include_pv_evals(self, sample_cache):
        table = build_pv_comparison_table(sample_cache, pv_depth=2)
        row = table[0]
        assert "pv1_eval_cp" in row
        assert "pvn_eval_cp" in row
        assert "eval_gap" in row

    def test_columns_include_structural_diff(self, sample_cache):
        table = build_pv_comparison_table(sample_cache, pv_depth=2)
        row = table[0]
        # Should have structural deltas between PV1 and PVN endpoints
        assert "diff_material_balance" in row
