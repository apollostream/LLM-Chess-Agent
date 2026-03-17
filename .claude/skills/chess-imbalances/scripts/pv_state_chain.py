"""Build structured feature tables from engine PV lines and game positions.

Three table-building modes:
1. Game-level transitions (absolute): consecutive positions with eval deltas.
2. PV comparison (absolute): PV1 vs PVN structural differences.
3. Game-level transitions (STM-relative): color-agnostic features + eval_advantage.

Usage:
    from pv_state_chain import build_game_transition_table, build_game_stm_table

    cache = json.load(open("analysis/game_cache/abc123.json"))
    game_table = build_game_transition_table(cache)           # absolute
    stm_table = build_game_stm_table(cache)                   # STM-relative
    pv_table = build_pv_comparison_table(cache, pv_depth=3)   # PV comparison
"""

from __future__ import annotations

import chess

from board_utils import analyze_position
from imbalance_vectorizer import (
    vectorize,
    vectorize_stm,
    compute_deltas,
    FEATURE_NAMES,
    STM_FEATURE_NAMES,
)


def replay_pv(
    board: chess.Board,
    pv_uci: list[str],
) -> list[dict]:
    """Replay PV moves on a board, collecting structural features at each step.

    Args:
        board: Starting position (not modified — a copy is used internally).
        pv_uci: List of UCI move strings (e.g., ["e2e4", "e7e5", "g1f3"]).

    Returns:
        List of row dicts. Row 0 is the root position (ply=0, no move/delta).
        Subsequent rows include the move played, features, and deltas from previous.
    """
    b = board.copy()
    rows: list[dict] = []
    prev_features: dict | None = None

    # Root position
    analysis = analyze_position(b)
    features = vectorize(analysis)
    row = {
        "ply": 0,
        "fen": b.fen(),
        "move_san": None,
        "move_uci": None,
        **features,
    }
    rows.append(row)
    prev_features = features

    # Replay each PV move
    for i, uci in enumerate(pv_uci):
        try:
            move = chess.Move.from_uci(uci)
            if move not in b.legal_moves:
                break
            san = b.san(move)
            b.push(move)
        except (ValueError, chess.InvalidMoveError):
            break

        analysis = analyze_position(b)
        features = vectorize(analysis)
        deltas = compute_deltas(prev_features, features)

        row = {
            "ply": i + 1,
            "fen": b.fen(),
            "move_san": san,
            "move_uci": uci,
            **features,
            **deltas,
        }
        rows.append(row)
        prev_features = features

    return rows


def build_game_transition_table(
    cache: dict,
    max_positions: int | None = None,
) -> list[dict]:
    """Build a transition table from game cache — one row per game position.

    Each row has: structural features, engine eval (cp), and deltas from previous.

    Args:
        cache: Deserialized game cache JSON (from game_store).
        max_positions: Optional limit on positions to process.

    Returns:
        List of row dicts with features, eval_cp, d_eval_cp, and deltas.
    """
    positions = cache.get("positions", [])
    engine_evals = cache.get("engine_evals", {})
    game_id = cache.get("pgn_hash", "unknown")[:12]

    if max_positions:
        positions = positions[:max_positions]

    rows: list[dict] = []
    prev_features: dict | None = None
    prev_eval_cp: int | None = None

    for i, fen in enumerate(positions):
        board = chess.Board(fen)
        analysis = analyze_position(board)
        features = vectorize(analysis)

        # Engine eval from cache
        ee = engine_evals.get(fen, {})
        ev = ee.get("eval") or {}
        eval_cp = ev.get("score_cp")  # may be None for mate positions

        row: dict = {
            "game_id": game_id,
            "position_index": i,
            "fen": fen,
            "eval_cp": eval_cp,
            **features,
        }

        if prev_features is not None:
            deltas = compute_deltas(prev_features, features)
            row.update(deltas)
            if prev_eval_cp is not None and eval_cp is not None:
                row["d_eval_cp"] = eval_cp - prev_eval_cp

        rows.append(row)
        prev_features = features
        prev_eval_cp = eval_cp

    return rows


def build_game_stm_table(
    cache: dict,
    max_positions: int | None = None,
) -> list[dict]:
    """Build a STM-relative transition table — color-agnostic features.

    Features are expressed as stm (side to move) vs opp (opponent).
    Eval is signed from STM perspective: positive = STM is ahead.
    Deltas represent the change caused by the move from STM's perspective.

    This representation collapses color-mirrored archetypes into universal
    move patterns — "gaining initiative" is the same whether White or Black.

    Args:
        cache: Deserialized game cache JSON.
        max_positions: Optional limit.

    Returns:
        List of row dicts with STM features, eval_stm, d_eval_stm, and deltas.
    """
    positions = cache.get("positions", [])
    engine_evals = cache.get("engine_evals", {})
    game_id = cache.get("pgn_hash", "unknown")[:12]

    if max_positions:
        positions = positions[:max_positions]

    rows: list[dict] = []
    prev_features: dict | None = None
    prev_eval_stm: int | float | None = None

    for i, fen in enumerate(positions):
        board = chess.Board(fen)
        is_white = board.turn == chess.WHITE

        # Inject engine data into analysis so vectorize_stm can read eval
        analysis = analyze_position(board)
        ee = engine_evals.get(fen, {})
        ev = ee.get("eval") or {}
        eval_cp = ev.get("score_cp")  # White perspective

        # Inject cached engine data for vectorize_stm to read
        analysis["engine"] = {"available": True, "eval": {"score_cp": eval_cp}}

        features = vectorize_stm(analysis)

        # Eval from STM perspective
        eval_stm: int | float | None = None
        if eval_cp is not None:
            eval_stm = eval_cp if is_white else -eval_cp

        row: dict = {
            "game_id": game_id,
            "position_index": i,
            "fen": fen,
            "eval_stm": eval_stm,
            **features,
        }

        if prev_features is not None:
            deltas = compute_deltas(prev_features, features)
            row.update(deltas)
            if prev_eval_stm is not None and eval_stm is not None:
                row["d_eval_stm"] = eval_stm - prev_eval_stm

        rows.append(row)
        prev_features = features
        prev_eval_stm = eval_stm

    return rows


def build_pv_comparison_table(
    cache: dict,
    pv_depth: int = 3,
    pv_n: int = -1,
    max_positions: int | None = None,
) -> list[dict]:
    """Compare PV1 vs PVN endpoints at each game position.

    For each position with multi-PV data, replays PV1 and PVN for `pv_depth`
    moves, then compares the structural features of the resulting positions.

    Args:
        cache: Deserialized game cache JSON.
        pv_depth: How many PV moves to replay (default 3).
        pv_n: Which PV to compare against PV1 (default -1 = last available).
        max_positions: Optional limit.

    Returns:
        List of row dicts with: root features, PV1/PVN endpoint features,
        structural diffs, and eval gap.
    """
    positions = cache.get("positions", [])
    engine_evals = cache.get("engine_evals", {})
    game_id = cache.get("pgn_hash", "unknown")[:12]

    if max_positions:
        positions = positions[:max_positions]

    rows: list[dict] = []

    for i, fen in enumerate(positions):
        ee = engine_evals.get(fen, {})
        top_lines = ee.get("top_lines") or []
        if len(top_lines) < 2:
            continue  # need at least 2 PV lines to compare

        pv1 = top_lines[0]
        pvn = top_lines[pv_n]  # last PV line by default

        pv1_uci = pv1.get("pv_uci", [])[:pv_depth]
        pvn_uci = pvn.get("pv_uci", [])[:pv_depth]

        if not pv1_uci or not pvn_uci:
            continue

        board = chess.Board(fen)

        # Replay PV1
        pv1_chain = replay_pv(board, pv1_uci)
        pv1_endpoint = pv1_chain[-1]

        # Replay PVN
        pvn_chain = replay_pv(board, pvn_uci)
        pvn_endpoint = pvn_chain[-1]

        # Root features
        root_features = {k: pv1_chain[0][k] for k in FEATURE_NAMES}

        # Structural difference between PV1 and PVN endpoints
        pv1_features = {k: pv1_endpoint[k] for k in FEATURE_NAMES}
        pvn_features = {k: pvn_endpoint[k] for k in FEATURE_NAMES}
        structural_diff = {f"diff_{k}": pv1_features[k] - pvn_features[k] for k in FEATURE_NAMES}

        pv1_eval_cp = pv1.get("score_cp")
        pvn_eval_cp = pvn.get("score_cp")
        eval_gap = None
        if pv1_eval_cp is not None and pvn_eval_cp is not None:
            eval_gap = pv1_eval_cp - pvn_eval_cp

        row = {
            "game_id": game_id,
            "position_index": i,
            "fen": fen,
            "pv1_eval_cp": pv1_eval_cp,
            "pvn_eval_cp": pvn_eval_cp,
            "eval_gap": eval_gap,
            "pv1_moves": " ".join(pv1_uci),
            "pvn_moves": " ".join(pvn_uci),
            "pv1_endpoint_fen": pv1_endpoint["fen"],
            "pvn_endpoint_fen": pvn_endpoint["fen"],
            **{f"root_{k}": v for k, v in root_features.items()},
            **{f"pv1_{k}": v for k, v in pv1_features.items()},
            **{f"pvn_{k}": v for k, v in pvn_features.items()},
            **structural_diff,
        }
        rows.append(row)

    return rows
