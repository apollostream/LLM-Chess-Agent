"""Tests for engine_eval.py — Stockfish engine integration.

Tests skip gracefully when Stockfish is not installed.
"""

import chess
import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "chess-imbalances" / "scripts"))
import engine_eval


# ── Fixtures ─────────────────────────────────────────────────────────────────

stockfish_path = engine_eval.find_stockfish()
requires_stockfish = pytest.mark.skipif(
    stockfish_path is None,
    reason="Stockfish not installed"
)


@pytest.fixture(scope="module")
def engine():
    """Module-scoped engine instance (opened once, shared across tests)."""
    eng = engine_eval.EngineEval()
    eng.open()
    if not eng.available:
        pytest.skip("Stockfish not available")
    yield eng
    eng.close()


# ── Discovery tests ──────────────────────────────────────────────────────────

class TestDiscovery:
    @requires_stockfish
    def test_find_stockfish(self):
        path = engine_eval.find_stockfish()
        assert path is not None
        assert "stockfish" in path.lower()

    def test_find_stockfish_returns_none_for_missing(self):
        """If we override search paths, should return None."""
        original = engine_eval.STOCKFISH_SEARCH_PATHS
        engine_eval.STOCKFISH_SEARCH_PATHS = ["/nonexistent/stockfish_xyz"]
        try:
            assert engine_eval.find_stockfish() is None
        finally:
            engine_eval.STOCKFISH_SEARCH_PATHS = original


# ── Graceful degradation ─────────────────────────────────────────────────────

class TestGracefulDegradation:
    def test_unavailable_engine_returns_none(self):
        """When Stockfish is not found, all methods return None."""
        eng = engine_eval.EngineEval(path="/nonexistent/stockfish")
        eng.open()
        assert eng.available is False

        board = chess.Board()
        assert eng.evaluate_position(board) is None
        assert eng.evaluate_multipv(board) is None
        assert eng.classify_move(board, chess.Move.from_uci("e2e4")) is None
        eng.close()

    def test_context_manager_unavailable(self):
        with engine_eval.EngineEval(path="/nonexistent/stockfish") as eng:
            assert eng.available is False
            assert eng.evaluate_position(chess.Board()) is None


# ── Utility tests ────────────────────────────────────────────────────────────

class TestUtilities:
    def test_score_display_positive(self):
        score = chess.engine.PovScore(chess.engine.Cp(150), chess.WHITE)
        assert engine_eval._score_display(score) == "+1.50"

    def test_score_display_negative(self):
        score = chess.engine.PovScore(chess.engine.Cp(-250), chess.WHITE)
        assert engine_eval._score_display(score) == "-2.50"

    def test_score_display_zero(self):
        score = chess.engine.PovScore(chess.engine.Cp(0), chess.WHITE)
        assert engine_eval._score_display(score) == "+0.00"

    def test_score_display_mate(self):
        score = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
        assert engine_eval._score_display(score) == "M3"

    def test_score_display_getting_mated(self):
        score = chess.engine.PovScore(chess.engine.Mate(-2), chess.WHITE)
        assert engine_eval._score_display(score) == "-M2"

    def test_classify_cp_loss(self):
        assert engine_eval._classify_cp_loss(0) == "best"
        assert engine_eval._classify_cp_loss(5) == "excellent"
        assert engine_eval._classify_cp_loss(15) == "good"
        assert engine_eval._classify_cp_loss(40) == "inaccuracy"
        assert engine_eval._classify_cp_loss(80) == "mistake"
        assert engine_eval._classify_cp_loss(150) == "blunder"
        assert engine_eval._classify_cp_loss(500) == "blunder"


# ── Evaluation tests ─────────────────────────────────────────────────────────

@requires_stockfish
class TestEvaluatePosition:
    def test_starting_position(self, engine):
        result = engine.evaluate_position(chess.Board(), depth=15)
        assert result is not None
        assert "score_cp" in result
        assert "score_display" in result
        assert "best_move" in result
        assert "pv" in result
        assert "depth" in result
        # Starting position should be roughly equal (within 1 pawn)
        assert abs(result["score_cp"]) < 100

    def test_pv_is_san(self, engine):
        result = engine.evaluate_position(chess.Board(), depth=12)
        assert len(result["pv"]) >= 1
        # First move should be recognizable SAN
        first = result["pv"][0]
        assert any(c.isalpha() for c in first)

    def test_mate_position(self, engine):
        """Position where White can force mate."""
        # Scholar's mate setup: 1 move to mate
        fen = "r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4"
        board = chess.Board(fen)
        # White just played Qxf7#, but let's check a pre-mate position
        # Actually this IS checkmate. Use one move before:
        fen2 = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 4 3"
        board2 = chess.Board(fen2)
        result = engine.evaluate_position(board2, depth=15)
        assert result is not None
        # Should find mate
        assert result["mate_in"] is not None and result["mate_in"] > 0

    def test_losing_position(self, engine):
        """Black is heavily losing (down a queen)."""
        fen = "rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen)
        result = engine.evaluate_position(board, depth=12)
        assert result is not None
        assert result["score_cp"] > 500  # White is way up

    def test_wdl_present(self, engine):
        result = engine.evaluate_position(chess.Board(), depth=12)
        # WDL may or may not be available depending on Stockfish version
        # SF16 should support it
        if result["wdl"] is not None:
            assert "win" in result["wdl"]
            assert "draw" in result["wdl"]
            assert "loss" in result["wdl"]
            assert result["wdl"]["win"] + result["wdl"]["draw"] + result["wdl"]["loss"] == 1000

    def test_best_move_uci(self, engine):
        result = engine.evaluate_position(chess.Board(), depth=12)
        assert result["best_move_uci"] is not None
        # Should be valid UCI format (4-5 chars)
        assert len(result["best_move_uci"]) in (4, 5)


@requires_stockfish
class TestEvaluateMultiPV:
    def test_three_lines(self, engine):
        lines = engine.evaluate_multipv(chess.Board(), num_lines=3, depth=12)
        assert lines is not None
        assert len(lines) == 3
        # Lines should be sorted by eval (best first)
        for line in lines:
            assert "score_cp" in line or line["mate_in"] is not None
            assert "best_move" in line
            assert "pv" in line

    def test_single_line(self, engine):
        lines = engine.evaluate_multipv(chess.Board(), num_lines=1, depth=12)
        assert len(lines) == 1

    def test_first_line_matches_single_eval(self, engine):
        """First multi-PV line should have same best move as single eval."""
        board = chess.Board()
        single = engine.evaluate_position(board, depth=15)
        multi = engine.evaluate_multipv(board, num_lines=3, depth=15)
        # Best move should be the same
        assert single["best_move"] == multi[0]["best_move"]


@requires_stockfish
class TestClassifyMove:
    def test_best_move_classified_well(self, engine):
        """The engine's best move should classify as best or excellent.

        Note: engine non-determinism means the best move from evaluate_position()
        may differ slightly from classify_move()'s internal eval. We allow
        'excellent' (≤10cp loss) as acceptable.
        """
        board = chess.Board()
        result = engine.evaluate_position(board, depth=15)
        best_move = chess.Move.from_uci(result["best_move_uci"])
        classification = engine.classify_move(board, best_move, depth=15)
        assert classification is not None
        assert classification["classification"] in ("best", "excellent")
        assert classification["cp_loss"] <= 10

    def test_blunder_detected(self, engine):
        """1. f3?? is a terrible opening move (weakens king, blocks knight)."""
        board = chess.Board()
        bad_move = chess.Move.from_uci("f2f3")
        classification = engine.classify_move(board, bad_move, depth=15)
        assert classification is not None
        # f3 should be at least an inaccuracy
        assert classification["classification"] in ("inaccuracy", "mistake", "blunder")
        assert classification["cp_loss"] > 20

    def test_classification_structure(self, engine):
        board = chess.Board()
        move = chess.Move.from_uci("e2e4")
        classification = engine.classify_move(board, move, depth=12)
        assert classification is not None
        assert "move" in classification
        assert "classification" in classification
        assert "cp_loss" in classification
        assert "eval_before" in classification
        assert "eval_after" in classification
        assert "best_move" in classification
        assert "is_best" in classification

    def test_classification_values_valid(self, engine):
        board = chess.Board()
        move = chess.Move.from_uci("e2e4")
        classification = engine.classify_move(board, move, depth=12)
        valid_labels = {"best", "excellent", "good", "inaccuracy", "mistake", "blunder"}
        assert classification["classification"] in valid_labels
        assert classification["cp_loss"] >= 0


# ── Context manager tests ────────────────────────────────────────────────────

@requires_stockfish
class TestContextManager:
    def test_context_manager_opens_and_closes(self):
        with engine_eval.EngineEval() as eng:
            assert eng.available is True
            result = eng.evaluate_position(chess.Board(), depth=8)
            assert result is not None
        # After exiting, engine should be closed
        assert eng.available is False

    def test_manual_open_close(self):
        eng = engine_eval.EngineEval()
        eng.open()
        assert eng.available is True
        eng.close()
        assert eng.available is False


# ── Integration: Jade-BOT position ──────────────────────────────────────────

@requires_stockfish
class TestJadeBotPosition:
    def test_jade_bot_move23_finds_bc6(self, engine):
        """The engine should identify Bc6 as one of the top moves."""
        fen = "4r1k1/1p1b1pp1/pp1pr2p/8/3p1q2/1P1B1Q1P/P1P2PK1/R5R1 b - - 0 23"
        board = chess.Board(fen)
        lines = engine.evaluate_multipv(board, num_lines=5, depth=18)
        assert lines is not None
        top_moves = [line["best_move"] for line in lines]
        # Bc6 should be among top 5 moves
        assert "Bc6" in top_moves, f"Bc6 not in top moves: {top_moves}"

    def test_jade_bot_eval_favors_black(self, engine):
        """Position after move 23 should strongly favor Black."""
        fen = "4r1k1/1p1b1pp1/pp1pr2p/8/3p1q2/1P1B1Q1P/P1P2PK1/R5R1 b - - 0 23"
        board = chess.Board(fen)
        result = engine.evaluate_position(board, depth=18)
        assert result is not None
        # Black is winning — eval should be negative (from White's perspective)
        assert result["score_cp"] is not None and result["score_cp"] < -200

    def test_qxf3_classification(self, engine):
        """23...Qxf3+ was played — classify it relative to Bc6."""
        fen = "4r1k1/1p1b1pp1/pp1pr2p/8/3p1q2/1P1B1Q1P/P1P2PK1/R5R1 b - - 0 23"
        board = chess.Board(fen)
        qxf3 = board.parse_san("Qxf3+")
        classification = engine.classify_move(board, qxf3, depth=18)
        assert classification is not None
        # Qxf3+ should not be the best move (Bc6 is better)
        # It might be "good" or "inaccuracy" depending on eval gap
        assert classification["cp_loss"] > 0
