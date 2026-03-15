"""Game-level engine evaluation cache — single source of truth.

Stores all Stockfish evaluations for every position in a game, computed
once in a single engine session.  All consumers (Engine tab, synopsis,
guides, critical moments) read from this cache.

Persists to disk so games survive backend restarts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from config import PROJECT_ROOT

ANALYSIS_DIR = PROJECT_ROOT / "analysis"
CACHE_DIR = ANALYSIS_DIR / "game_cache"


def pgn_hash(pgn: str) -> str:
    """Deterministic SHA-256 hash of PGN text."""
    return hashlib.sha256(pgn.strip().encode()).hexdigest()


@dataclass
class GameStore:
    """All cached data for a single game."""

    pgn: str
    pgn_hash: str                          # SHA-256 for identity/disk naming
    positions: list[str]                   # ordered FENs, start → end
    depth: int
    lines: int
    engine_evals: dict[str, dict]          # FEN → {"eval": {...}, "top_lines": [...]}
    critical_moments_all: list[dict]       # all detected candidates
    critical_moments_selected: list[dict]  # auto-selected top-N subset
    synopsis_text: str | None = None


# Module-level singleton (one game at a time, matching single-game UI)
active_game: GameStore | None = None


def clear_active() -> None:
    """Clear the active game cache."""
    global active_game
    active_game = None


def save_to_disk(store: GameStore) -> Path:
    """Serialize GameStore to disk as JSON."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{store.pgn_hash[:12]}.json"
    path = CACHE_DIR / filename
    data = asdict(store)
    path.write_text(json.dumps(data, indent=None, separators=(",", ":")))
    return path


def load_from_disk(
    hash_value: str,
    depth: int | None = None,
    lines: int | None = None,
) -> GameStore | None:
    """Load a cached game from disk by PGN hash.

    If depth/lines are provided, only returns the cache when they match.
    Returns None if not found or parameters don't match.
    """
    filename = f"{hash_value[:12]}.json"
    path = CACHE_DIR / filename
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    # Check depth/lines match if specified
    if depth is not None and data.get("depth") != depth:
        return None
    if lines is not None and data.get("lines") != lines:
        return None

    return GameStore(
        pgn=data["pgn"],
        pgn_hash=data["pgn_hash"],
        positions=data["positions"],
        depth=data["depth"],
        lines=data["lines"],
        engine_evals=data["engine_evals"],
        critical_moments_all=data.get("critical_moments_all", []),
        critical_moments_selected=data.get("critical_moments_selected", []),
        synopsis_text=data.get("synopsis_text"),
    )
