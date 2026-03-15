"""Tests for GameStore data model and disk persistence."""

import json
import shutil
from pathlib import Path

import pytest

# Add backend to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web" / "backend"))

from services import game_store


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    """Reset active_game and redirect disk cache to tmp_path."""
    game_store.clear_active()
    monkeypatch.setattr(game_store, "CACHE_DIR", tmp_path)
    yield
    game_store.clear_active()


def _make_store(**overrides) -> game_store.GameStore:
    defaults = dict(
        pgn='[Event "Test"]\n1. e4 e5 *',
        pgn_hash="abc123def456",
        positions=[
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
            "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2",
        ],
        depth=20,
        lines=3,
        engine_evals={
            "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1": {
                "available": True,
                "eval": {"score_cp": 30, "best_move": "e5"},
                "top_lines": [{"best_move": "e5", "score_cp": 30}],
            },
        },
        critical_moments_all=[],
        critical_moments_selected=[],
    )
    defaults.update(overrides)
    return game_store.GameStore(**defaults)


class TestGameStoreSaveLoad:
    def test_roundtrip(self, tmp_path, monkeypatch):
        """Save to disk, load back, evals match."""
        monkeypatch.setattr(game_store, "CACHE_DIR", tmp_path)
        store = _make_store()
        path = game_store.save_to_disk(store)

        assert path.exists()
        loaded = game_store.load_from_disk(store.pgn_hash)
        assert loaded is not None
        assert loaded.pgn == store.pgn
        assert loaded.pgn_hash == store.pgn_hash
        assert loaded.positions == store.positions
        assert loaded.depth == store.depth
        assert loaded.lines == store.lines
        assert loaded.engine_evals == store.engine_evals
        assert loaded.synopsis_text == store.synopsis_text

    def test_clear(self):
        """Clear sets active_game to None."""
        game_store.active_game = _make_store()
        assert game_store.active_game is not None
        game_store.clear_active()
        assert game_store.active_game is None

    def test_pgn_hash_deterministic(self):
        """Same PGN always produces same hash."""
        pgn = '[Event "Test"]\n1. e4 e5 2. Nf3 *'
        h1 = game_store.pgn_hash(pgn)
        h2 = game_store.pgn_hash(pgn)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_load_nonexistent(self, tmp_path, monkeypatch):
        """Returns None gracefully for unknown hash."""
        monkeypatch.setattr(game_store, "CACHE_DIR", tmp_path)
        result = game_store.load_from_disk("nonexistent_hash_value")
        assert result is None

    def test_roundtrip_with_synopsis(self, tmp_path, monkeypatch):
        """Synopsis text survives roundtrip."""
        monkeypatch.setattr(game_store, "CACHE_DIR", tmp_path)
        store = _make_store(synopsis_text="A great game synopsis.")
        game_store.save_to_disk(store)
        loaded = game_store.load_from_disk(store.pgn_hash)
        assert loaded is not None
        assert loaded.synopsis_text == "A great game synopsis."

    def test_matching_depth_lines(self, tmp_path, monkeypatch):
        """load_from_disk checks depth/lines match."""
        monkeypatch.setattr(game_store, "CACHE_DIR", tmp_path)
        store = _make_store(depth=20, lines=3)
        game_store.save_to_disk(store)

        # Same hash but requesting different depth won't match
        loaded = game_store.load_from_disk(store.pgn_hash, depth=25, lines=3)
        assert loaded is None

        # Matching depth/lines works
        loaded = game_store.load_from_disk(store.pgn_hash, depth=20, lines=3)
        assert loaded is not None
