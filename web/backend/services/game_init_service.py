"""Game initialization pipeline — evaluate all positions once, detect moments.

Orchestrates: PGN parse → single-session Stockfish eval → critical moments.
Results cached in game_store for all downstream consumers.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from collections.abc import AsyncIterator

import chess
import chess.pgn

from config import GAME_INIT_DEPTH_DEFAULT, GAME_INIT_LINES_DEFAULT, SCRIPTS_DIR
from services import game_store
from services.agent_service import _sse
from services.cache import analysis_cache, engine_cache

# Add scripts dir for engine_eval and game_narrative imports
_scripts_str = str(SCRIPTS_DIR)
if _scripts_str not in sys.path:
    sys.path.insert(0, _scripts_str)

from engine_eval import EngineEval  # noqa: E402
from game_narrative import detect_critical_moments_from_cache  # noqa: E402


def _extract_fens(pgn_text: str) -> list[str]:
    """Parse PGN and return all FENs from start to end position."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return []

    board = game.board()
    fens = [board.fen()]
    for move in game.mainline_moves():
        board.push(move)
        fens.append(board.fen())
    return fens


def _evaluate_all_sync(
    engine: "EngineEval",
    fens: list[str],
    depth: int,
    lines: int,
    progress_callback=None,
) -> dict[str, dict]:
    """Evaluate all positions in a single engine session (blocking).

    Args:
        engine: An already-opened EngineEval instance.
        fens: List of FEN strings to evaluate.
        depth: Search depth.
        lines: Number of multi-PV lines.
        progress_callback: Optional callable(current, total) for progress reporting.

    Returns:
        Dict mapping FEN → {"eval": {...}, "top_lines": [...]}
    """
    results: dict[str, dict] = {}

    for i, fen in enumerate(fens):
        if fen in results:
            # Skip duplicate positions (e.g., repetitions)
            if progress_callback:
                progress_callback(i + 1, len(fens))
            continue

        board = chess.Board(fen)
        multi = engine.evaluate_multipv(board, num_lines=lines, depth=depth)

        # Use multi-PV top line as the single-PV equivalent — one call
        # instead of two, since single-PV was always overridden anyway.
        single = multi[0] if multi and len(multi) > 0 else None

        results[fen] = {"available": True, "eval": single, "top_lines": multi}

        if progress_callback:
            progress_callback(i + 1, len(fens))

    return results


def _select_top_moments(moments: list[dict], n: int = 5) -> list[dict]:
    """Auto-select the top N moments by eval swing magnitude."""
    sorted_moments = sorted(moments, key=lambda m: abs(m.get("delta_cp", 0)), reverse=True)
    selected = sorted_moments[:n]
    # Re-sort by move order for display
    return sorted(selected, key=lambda m: (m.get("move_number", 0), 0 if m.get("side") == "white" else 1))


async def initialize_game(
    pgn: str,
    depth: int = GAME_INIT_DEPTH_DEFAULT,
    lines: int = GAME_INIT_LINES_DEFAULT,
    threshold_cp: int = 50,
    decay_scale_cp: int | None = 750,
) -> AsyncIterator[str]:
    """Run the full game initialization pipeline, yielding SSE events.

    Phases:
    1. Parse PGN → extract all FENs
    2. Single EngineEval session → evaluate every position
    3. Detect critical moments from cached evals
    4. Yield done event with moments + game_id

    Checks disk cache first — if found, skips evaluation.
    """
    # --- Phase 1: Parse PGN ---
    fens = _extract_fens(pgn)
    if not fens:
        yield _sse({"type": "error", "content": "Failed to parse PGN"})
        return

    hash_value = game_store.pgn_hash(pgn)
    total = len(fens)

    yield _sse({"type": "progress", "phase": "parse", "current": total, "total": total})

    # --- Check disk cache ---
    cached = game_store.load_from_disk(hash_value, depth=depth, lines=lines)
    if cached is not None:
        game_store.active_game = cached
        analysis_cache.clear()
        engine_cache.clear()
        yield _sse({
            "type": "cached",
            "game_id": hash_value[:12],
            "positions": total,
        })
        yield _sse({
            "type": "done",
            "game_id": hash_value[:12],
            "moments": cached.critical_moments_selected,
            "moments_all": cached.critical_moments_all,
            "positions": total,
        })
        return

    # --- Phase 2: Evaluate all positions ---
    progress_queue: asyncio.Queue[int] = asyncio.Queue()

    def _progress_callback(current: int, total_n: int) -> None:
        progress_queue.put_nowait(current)

    async def _run_eval() -> dict[str, dict]:
        def _worker():
            # Use more resources for bulk evaluation — 2 threads and 256MB hash
            # gives Stockfish better transposition table reuse across sequential
            # positions while leaving cores free for the rest of the app.
            with EngineEval(threads=2, hash_mb=256) as engine:
                if not engine.available:
                    return {}
                return _evaluate_all_sync(engine, fens, depth, lines, _progress_callback)
        return await asyncio.to_thread(_worker)

    # Run evaluation in background, stream progress
    eval_task = asyncio.create_task(_run_eval())

    # Yield progress events as they come in
    while not eval_task.done():
        try:
            current = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
            yield _sse({"type": "progress", "phase": "engine", "current": current, "total": total})
        except asyncio.TimeoutError:
            continue

    # Drain any remaining progress events
    while not progress_queue.empty():
        current = progress_queue.get_nowait()
        yield _sse({"type": "progress", "phase": "engine", "current": current, "total": total})

    engine_evals = await eval_task
    if not engine_evals:
        yield _sse({"type": "error", "content": "Stockfish engine not available"})
        return

    # --- Phase 3: Detect critical moments ---
    yield _sse({"type": "progress", "phase": "moments", "current": 0, "total": 1})

    moments_objs = detect_critical_moments_from_cache(
        pgn, engine_evals,
        threshold_cp=threshold_cp,
        decay_scale_cp=decay_scale_cp,
    )
    moments_all = [m.model_dump() for m in moments_objs]
    moments_selected = _select_top_moments(moments_all, n=5)

    yield _sse({"type": "progress", "phase": "moments", "current": 1, "total": 1})

    # --- Phase 4: Populate game store ---
    store = game_store.GameStore(
        pgn=pgn,
        pgn_hash=hash_value,
        positions=fens,
        depth=depth,
        lines=lines,
        engine_evals=engine_evals,
        critical_moments_all=moments_all,
        critical_moments_selected=moments_selected,
    )
    game_store.active_game = store

    # Clear stale per-position caches so consumers re-fetch with game cache data
    analysis_cache.clear()
    engine_cache.clear()

    # Persist to disk
    game_store.save_to_disk(store)

    yield _sse({
        "type": "done",
        "game_id": hash_value[:12],
        "moments": moments_selected,
        "moments_all": moments_all,
        "positions": total,
    })
