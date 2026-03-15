"""Tests for game init service and endpoint."""

import asyncio
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web" / "backend"))

from services import game_store

# Simple 4-ply game
SIMPLE_PGN = '[Event "Test"]\n[Result "*"]\n\n1. e4 e5 2. Nf3 Nc6 *'


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    game_store.clear_active()
    monkeypatch.setattr(game_store, "CACHE_DIR", tmp_path)
    yield
    game_store.clear_active()


def _mock_engine_eval():
    """Create a mock EngineEval that returns deterministic results."""
    engine = MagicMock()
    engine.available = True
    engine.__enter__ = MagicMock(return_value=engine)
    engine.__exit__ = MagicMock(return_value=False)

    call_count = {"n": 0}

    def mock_multipv(board, num_lines=3, depth=20):
        call_count["n"] += 1
        cp = call_count["n"] * 10
        return [
            {"best_move": "e4", "best_move_uci": "e2e4", "score_cp": cp,
             "score_display": f"+{cp/100:.2f}", "pv": ["e4"], "pv_uci": ["e2e4"]},
        ]

    def mock_single(board, depth=20):
        cp = call_count["n"] * 10
        return {
            "score_cp": cp, "best_move": "e4", "best_move_uci": "e2e4",
            "score_display": f"+{cp/100:.2f}", "pv": ["e4"], "pv_uci": ["e2e4"],
            "mate_in": None, "wdl": None, "depth": depth,
        }

    engine.evaluate_multipv = mock_multipv
    engine.evaluate_position = mock_single
    return engine


class TestGameInit:
    def test_evaluates_all_positions(self):
        """All FENs in the game get engine evaluations."""
        from services.game_init_service import _evaluate_all_sync

        engine = _mock_engine_eval()
        import chess
        import chess.pgn

        game = chess.pgn.read_game(io.StringIO(SIMPLE_PGN))
        board = game.board()
        fens = [board.fen()]
        for move in game.mainline_moves():
            board.push(move)
            fens.append(board.fen())

        results = _evaluate_all_sync(engine, fens, depth=20, lines=3)
        assert len(results) == len(fens)
        for fen in fens:
            assert fen in results
            assert "eval" in results[fen]
            assert "top_lines" in results[fen]

    @pytest.mark.asyncio
    async def test_yields_progress(self):
        """SSE events have correct format and counts."""
        from services.game_init_service import initialize_game

        engine = _mock_engine_eval()
        with patch("services.game_init_service.EngineEval", return_value=engine):
            events = []
            async for chunk in initialize_game(SIMPLE_PGN, depth=20, lines=3):
                if chunk.startswith("data: "):
                    try:
                        event = json.loads(chunk[6:].rstrip("\n"))
                        events.append(event)
                    except json.JSONDecodeError:
                        pass

        # Should have engine progress events
        engine_events = [e for e in events if e.get("phase") == "engine"]
        assert len(engine_events) > 0
        # Last engine event should have current == total
        last_engine = engine_events[-1]
        assert last_engine["current"] == last_engine["total"]

        # Should have a done event
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        assert "moments" in done_events[0]
        assert "game_id" in done_events[0]

    @pytest.mark.asyncio
    async def test_detects_moments(self):
        """Moments returned in final done event."""
        from services.game_init_service import initialize_game

        engine = _mock_engine_eval()
        with patch("services.game_init_service.EngineEval", return_value=engine):
            done_event = None
            async for chunk in initialize_game(SIMPLE_PGN, depth=20, lines=3):
                if chunk.startswith("data: "):
                    try:
                        event = json.loads(chunk[6:].rstrip("\n"))
                        if event.get("type") == "done":
                            done_event = event
                    except json.JSONDecodeError:
                        pass

        assert done_event is not None
        assert isinstance(done_event["moments"], list)

    @pytest.mark.asyncio
    async def test_populates_active_game(self):
        """After init, game_store.active_game is populated."""
        from services.game_init_service import initialize_game

        engine = _mock_engine_eval()
        with patch("services.game_init_service.EngineEval", return_value=engine):
            async for _ in initialize_game(SIMPLE_PGN, depth=20, lines=3):
                pass

        assert game_store.active_game is not None
        assert game_store.active_game.pgn == SIMPLE_PGN
        assert len(game_store.active_game.positions) == 5  # start + 4 moves
        assert len(game_store.active_game.engine_evals) == 5

    @pytest.mark.asyncio
    async def test_disk_cache_hit(self, tmp_path, monkeypatch):
        """Returns cached game without re-evaluating."""
        from services.game_init_service import initialize_game

        monkeypatch.setattr(game_store, "CACHE_DIR", tmp_path)

        # First: run the init to populate cache
        engine = _mock_engine_eval()
        with patch("services.game_init_service.EngineEval", return_value=engine):
            async for _ in initialize_game(SIMPLE_PGN, depth=20, lines=3):
                pass

        # Save to disk
        game_store.save_to_disk(game_store.active_game)
        game_store.clear_active()

        # Second: should hit disk cache — no EngineEval needed
        events = []
        # Don't mock EngineEval — if it tries to call it, it would fail
        with patch("services.game_init_service.EngineEval", side_effect=RuntimeError("should not call")):
            async for chunk in initialize_game(SIMPLE_PGN, depth=20, lines=3):
                if chunk.startswith("data: "):
                    try:
                        events.append(json.loads(chunk[6:].rstrip("\n")))
                    except json.JSONDecodeError:
                        pass

        # Should have a cached event
        cached_events = [e for e in events if e.get("type") == "cached"]
        assert len(cached_events) == 1
        assert game_store.active_game is not None
