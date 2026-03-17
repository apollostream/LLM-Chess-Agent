"""Bridge to the existing chess analysis pipeline.

Adds the scripts directory to sys.path so we can import board_utils,
tactical_motifs, and engine_eval directly.
"""

from __future__ import annotations

import json
import sys

import chess

from config import SCRIPTS_DIR

# Add scripts dir to path for imports
_scripts_str = str(SCRIPTS_DIR)
if _scripts_str not in sys.path:
    sys.path.insert(0, _scripts_str)

import board_utils  # noqa: E402
import tactical_motifs  # noqa: E402
from engine_eval import EngineEval  # noqa: E402
from imbalance_vectorizer import vectorize_stm  # noqa: E402


def analyze_position(fen: str, use_engine: bool = False,
                     depth: int = 20, lines: int = 3) -> dict:
    """Run full imbalance analysis on a FEN position."""
    board = chess.Board(fen)
    if use_engine:
        with EngineEval() as engine:
            return board_utils.analyze_position(
                board, engine=engine, engine_depth=depth, engine_lines=lines
            )
    return board_utils.analyze_position(board)


def analyze_pv_endpoint(fen: str, pv_uci: list[str]) -> dict | None:
    """Play PV moves from FEN and analyze the endpoint position.

    Returns full analyze_position() output at the PV endpoint, or None on error.
    """
    try:
        board = chess.Board(fen)
        for uci in pv_uci:
            board.push(chess.Move.from_uci(uci))
        return board_utils.analyze_position(board)
    except Exception:
        return None


def _swap_perspective(vec: dict) -> dict:
    """Swap STM/OPP features to align with the opposite side's perspective."""
    swapped = {}
    for k, v in vec.items():
        if k.endswith("_stm"):
            opp_key = k[:-4] + "_opp"
            swapped[k] = vec.get(opp_key, 0)
        elif k.endswith("_opp"):
            stm_key = k[:-4] + "_stm"
            swapped[k] = vec.get(stm_key, 0)
        elif k in ("material_advantage", "eval_advantage"):
            swapped[k] = -v
        else:
            swapped[k] = v
    return swapped


# Feature tiers for the playbook (empirical hierarchy from precision matrix)
_HUB_FEATURES = {
    "material_advantage", "initiative_score_stm", "initiative_score_opp",
    "pawn_count_stm", "pawn_count_opp", "dynamic_score_stm", "dynamic_score_opp",
    "static_score_stm", "static_score_opp", "space_stm", "space_opp",
}
_TACTICAL_FEATURES = {
    "fork_threats_stm", "fork_threats_opp",
    "skewer_threats_stm", "skewer_threats_opp",
    "discovered_attack_threats_stm", "discovered_attack_threats_opp",
    "checkmate_threats_stm", "checkmate_threats_opp",
    "checks_available_stm", "checks_available_opp",
    "mate_threat_by_stm", "mate_threat_by_opp",
    "pin_count", "battery_count", "hanging_pieces_count", "trapped_pieces_count",
}
_BRIDGE_FEATURES = {
    "passed_pawns_stm", "passed_pawns_opp",
    "semi_open_files_stm", "semi_open_files_opp",
    "queen_count_stm", "queen_count_opp",
    "rook_count_stm", "rook_count_opp",
}
_STRUCTURAL_FEATURES = {
    "isolated_pawns_stm", "isolated_pawns_opp",
    "doubled_pawns_stm", "doubled_pawns_opp",
    "backward_pawns_stm", "backward_pawns_opp",
    "development_stm", "development_opp",
    "castling_rights_stm", "castling_rights_opp",
    "king_attackers_stm", "king_attackers_opp",
    "pawn_shield_stm", "pawn_shield_opp",
    "missing_shield_stm", "missing_shield_opp",
}
_SKIP_FEATURES = {"eval_advantage", "is_check", "game_phase", "total_non_pawn_material"}


def _tier_label(key: str) -> tuple[int, str]:
    """Return (sort_order, label) for a feature key."""
    if key in _HUB_FEATURES:
        return 0, "HUB FEATURES (assess first — broadest explanatory reach)"
    if key in _TACTICAL_FEATURES:
        return 1, "TACTICAL MOTIF CHANGES"
    if key in _BRIDGE_FEATURES:
        return 2, "BRIDGE FEATURES (connect hubs to specifics)"
    if key in _STRUCTURAL_FEATURES:
        return 3, "STRUCTURAL FEATURES (pawn structure, king safety, development)"
    return 4, "OTHER FEATURES"


def _format_tactical_motifs(analysis: dict, perspective: str) -> str:
    """Format raw tactical motif details from an analysis dict."""
    tac = analysis.get("tactics", {})
    lines = []

    static = tac.get("static", {})
    for category, label in [
        ("pins", "Pins"), ("batteries", "Batteries"),
        ("hanging_pieces", "Hanging pieces"), ("trapped_pieces", "Trapped pieces"),
        ("x_rays", "X-rays"),
    ]:
        items = static.get(category, [])
        if items:
            descs = []
            for item in items[:5]:  # limit to 5 per type
                if isinstance(item, dict):
                    parts = []
                    if "attacker" in item:
                        parts.append(item["attacker"])
                    if "type" in item:
                        parts.append(f"({item['type']})")
                    if "square" in item:
                        parts.append(f"on {item['square']}")
                    if "target" in item:
                        parts.append(f"→ {item['target']}")
                    descs.append(" ".join(parts))
                else:
                    descs.append(str(item))
            lines.append(f"  {label}: {'; '.join(descs)}")

    for threat_key, threat_label in [("threats", perspective), ("opponent_threats", f"opponent of {perspective}")]:
        threats = tac.get(threat_key, {})
        for category, label in [
            ("forks", "Fork threats"), ("skewers", "Skewer threats"),
            ("discovered_attacks", "Discovered attacks"),
            ("checkmate_threats", "Checkmate threats"),
        ]:
            items = threats.get(category, [])
            if items:
                descs = []
                for item in items[:5]:
                    if isinstance(item, dict):
                        parts = []
                        if "attacker" in item:
                            parts.append(item["attacker"])
                        if "square" in item:
                            parts.append(f"on {item['square']}")
                        targets = item.get("targets", [])
                        if targets:
                            parts.append(f"→ {', '.join(str(t) for t in targets[:3])}")
                        elif "target" in item:
                            parts.append(f"→ {item['target']}")
                        if "side" in item:
                            parts.append(f"[{item['side']}]")
                        descs.append(" ".join(parts))
                    else:
                        descs.append(str(item))
                lines.append(f"  {label} ({threat_label}): {'; '.join(descs)}")

    return "\n".join(lines) if lines else "  (none detected)"


def compute_pv_context(fen: str, analysis_p0: dict, engine_json_str: str) -> str | None:
    """Compute PV endpoint features, deltas, and tactical changes.

    Returns a formatted string for injection into the Player's Guide prompt,
    or None if no PV is available.
    """
    # Parse engine JSON to get the top PV
    try:
        engine_data = json.loads(engine_json_str) if isinstance(engine_json_str, str) else engine_json_str
    except (json.JSONDecodeError, TypeError):
        return None

    top_lines = engine_data.get("top_lines", [])
    if not top_lines:
        return None

    pv_moves = top_lines[0].get("pv", [])
    if not pv_moves:
        return None

    # Analyze PV endpoint
    analysis_pn = analyze_pv_endpoint(fen, pv_moves)
    if analysis_pn is None:
        return None

    # Vectorize both positions from initial STM's perspective
    vec_p0 = vectorize_stm(analysis_p0)
    vec_pn_raw = vectorize_stm(analysis_pn)

    p0_is_white = analysis_p0.get("side_to_move") == "white"
    pn_is_white = analysis_pn.get("side_to_move") == "white"
    vec_pn = vec_pn_raw if (p0_is_white == pn_is_white) else _swap_perspective(vec_pn_raw)

    stm_color = "White" if p0_is_white else "Black"

    # Compute deltas, group by tier
    tier_deltas: dict[str, list[str]] = {}
    for key in vec_p0:
        if key in _SKIP_FEATURES:
            continue
        val_p0 = vec_p0.get(key, 0)
        val_pn = vec_pn.get(key, 0)
        delta = val_pn - val_p0
        if abs(delta) < 1e-10:
            continue

        order, label = _tier_label(key)
        if label not in tier_deltas:
            tier_deltas[label] = []
        sign = "+" if delta > 0 else ""

        # Format value display
        if isinstance(val_p0, float) or isinstance(val_pn, float):
            tier_deltas[label].append(
                f"  {key:40s}  {val_p0:>7.1f} → {val_pn:>7.1f}  (Δ = {sign}{delta:.1f})"
            )
        else:
            tier_deltas[label].append(
                f"  {key:40s}  {val_p0:>7} → {val_pn:>7}  (Δ = {sign}{delta})"
            )

    # Build PV endpoint FEN
    board_pn = chess.Board(fen)
    for uci in pv_moves:
        board_pn.push(chess.Move.from_uci(uci))
    pv_fen = board_pn.fen()

    # Format PV moves as SAN for readability
    pv_san = []
    board_tmp = chess.Board(fen)
    for uci in pv_moves:
        move = chess.Move.from_uci(uci)
        pv_san.append(board_tmp.san(move))
        board_tmp.push(move)

    # Game phase context
    phase = vec_p0.get("game_phase", 0)
    if phase < 0.3:
        phase_name = "Opening"
    elif phase < 0.7:
        phase_name = "Middlegame"
    else:
        phase_name = "Endgame"

    # Assemble output
    parts = []
    parts.append(f"\n=== PV ANALYSIS: IMPLICATIVE REASONING DATA ===")
    parts.append(f"PV ({len(pv_moves)} half-moves): {' '.join(pv_san)}")
    parts.append(f"PV endpoint FEN: {pv_fen}")
    parts.append(f"Perspective: {stm_color} (side to move at P₀)")
    parts.append(f"Game phase: {phase_name} ({phase:.2f})")
    parts.append("")

    if tier_deltas:
        parts.append("--- FEATURE DELTAS (P₀ → PV endpoint) ---")
        # Sort tiers by order
        ordered = sorted(tier_deltas.items(), key=lambda x: _tier_label_order(x[0]))
        for label, lines in ordered:
            parts.append(f"\n{label}:")
            for line in lines:
                parts.append(line)
        parts.append("\n(Only non-zero deltas shown.)")
    else:
        parts.append("No significant feature changes detected along this PV.")

    parts.append("")
    parts.append(f"--- TACTICAL MOTIFS AT CURRENT POSITION (P₀) ---")
    parts.append(_format_tactical_motifs(analysis_p0, stm_color))

    parts.append("")
    parts.append(f"--- TACTICAL MOTIFS AT PV ENDPOINT (P_n) ---")
    parts.append(_format_tactical_motifs(analysis_pn, stm_color if p0_is_white == pn_is_white else ("Black" if stm_color == "White" else "White")))

    return "\n".join(parts)


def _tier_label_order(label: str) -> int:
    """Sort order for tier labels."""
    if "HUB" in label:
        return 0
    if "TACTICAL" in label:
        return 1
    if "BRIDGE" in label:
        return 2
    if "STRUCTURAL" in label:
        return 3
    return 4


def analyze_tactics(fen: str) -> dict:
    """Run tactical motif detection on a FEN position."""
    board = chess.Board(fen)
    return tactical_motifs.analyze_tactics(board)


def evaluate_position(fen: str, depth: int = 20, lines: int = 3) -> dict | None:
    """Run engine evaluation on a FEN position."""
    board = chess.Board(fen)
    with EngineEval() as engine:
        result = engine.evaluate_multipv(board, num_lines=lines, depth=depth)

    # Use multi-PV top line as single-PV equivalent — one call instead of
    # two, since single-PV was always overridden by multi-PV[0] anyway.
    single = result[0] if result and len(result) > 0 else None

    return {
        "eval": single,
        "top_lines": result,
    }


def classify_move(fen: str, move_san: str, depth: int = 20) -> dict | None:
    """Classify a move's quality."""
    board = chess.Board(fen)
    move = board.parse_san(move_san)
    with EngineEval() as engine:
        return engine.classify_move(board, move, depth=depth)
