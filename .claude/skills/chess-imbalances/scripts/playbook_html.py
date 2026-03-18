"""Generate an HTML Player's Guide document for a chess position.

Takes a FEN string, runs the full analysis pipeline (board_utils, tactical_motifs,
engine_eval, imbalance_vectorizer, compute_pv_context), and renders a rich HTML
document with board SVG, imbalances, tactical motifs, PV feature deltas, and a
template for the Player's Guide narrative.

Usage:
    python playbook_html.py "<FEN>" [--depth 22] [--lines 3] [--output path.html] [--open]
    python playbook_html.py "<FEN>" --guide-text guide.md  # inject pre-written guide text
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

import chess
import chess.svg

# Ensure scripts dir is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import board_utils
import tactical_motifs
from engine_eval import EngineEval
from imbalance_vectorizer import vectorize_stm

# Reuse PV context machinery from the web backend
_WEB_BACKEND = _SCRIPTS_DIR.parent.parent.parent / "web" / "backend"
if str(_WEB_BACKEND) not in sys.path:
    sys.path.insert(0, str(_WEB_BACKEND))


# ── Helper formatters ────────────────────────────────────────────────────────

def _fmt_pieces(mat: dict, color: str) -> str:
    """Format piece list from material analysis dict."""
    pieces = mat.get(color, {})
    parts = []
    for name, key in [("Q", "queens"), ("R", "rooks"), ("B", "bishops"), ("N", "knights")]:
        count = pieces.get(key, 0)
        if count:
            parts.append(f"{count}{name}")
    pawns = pieces.get("pawns", 0)
    if pawns:
        parts.append(f"{pawns}P")
    if pieces.get("bishop_pair"):
        parts.append("+ bishop pair")
    return ", ".join(parts) if parts else "—"


def _fmt_shield(shield_list) -> str:
    """Format pawn shield squares list."""
    if isinstance(shield_list, list):
        return ", ".join(shield_list) if shield_list else "none"
    return str(shield_list) if shield_list else "none"


def _fmt_attackers(attackers) -> str:
    """Format nearby attackers."""
    if isinstance(attackers, list):
        return str(len(attackers))
    return str(attackers) if attackers else "0"


def _fmt_castling(ks: dict) -> str:
    """Format castling status."""
    castled = ks.get("has_castled", False)
    if castled:
        return "Castled"
    rights = ks.get("castling_rights", {})
    sides = []
    if rights.get("kingside"):
        sides.append("K-side")
    if rights.get("queenside"):
        sides.append("Q-side")
    if sides:
        return f"Not yet (rights: {', '.join(sides)})"
    return "Not castled (no rights)"


def _fmt_undeveloped(dev: dict, color: str) -> str:
    """Format undeveloped pieces list."""
    undeveloped = dev.get(color, {}).get("undeveloped_pieces", [])
    if not undeveloped:
        return "—"
    parts = []
    for p in undeveloped:
        if isinstance(p, dict):
            parts.append(f"{p.get('piece', '?')} on {p.get('square', '?')}")
        else:
            parts.append(str(p))
    return ", ".join(parts)


def _phase_name(phase_val: float) -> str:
    if phase_val < 0.3:
        return "Opening"
    elif phase_val < 0.7:
        return "Middlegame"
    return "Endgame"


def _eval_color(score: float) -> str:
    if score > 0.5:
        return "#27ae60"
    elif score < -0.5:
        return "#c0392b"
    return "#777"


def _eval_description(score: float) -> str:
    abs_s = abs(score)
    if abs_s < 0.3:
        return "Equal position"
    color = "White" if score > 0 else "Black"
    if abs_s < 1.0:
        return f"Slight edge for {color}"
    if abs_s < 2.0:
        return f"{color} is better"
    if abs_s < 4.0:
        return f"{color} has a clear advantage"
    return f"{color} is winning decisively"


# ── Tactical motifs formatting ───────────────────────────────────────────────

def _fmt_tactics_static(tac: dict) -> list[tuple[str, str]]:
    """Return list of (pattern_name, details_html) for static patterns.

    Each motif type maps to its own key schema from tactical_motifs.py.
    """
    static = tac.get("static", {})
    rows = []

    # Pins: pinner, pinned_piece, pinned_to, pin_type, pinned_side
    pins = static.get("pins", [])
    if pins:
        descs = []
        for p in pins[:5]:
            if isinstance(p, dict):
                descs.append(
                    f"{p.get('pinner', '?')} pins {p.get('pinned_piece', '?')}"
                    f" to {p.get('pinned_to', '?')} ({p.get('pin_type', '?')})"
                )
            else:
                descs.append(str(p))
        rows.append(("Pins", "<br>".join(descs)))
    else:
        rows.append(("Pins", "<em>none</em>"))

    # Batteries: pieces (list), line, side
    batteries = static.get("batteries", [])
    if batteries:
        descs = []
        for b in batteries[:5]:
            if isinstance(b, dict):
                pieces = b.get("pieces", [])
                descs.append(f"{' + '.join(pieces)} ({b.get('line', '?')}) [{b.get('side', '')}]")
            else:
                descs.append(str(b))
        rows.append(("Batteries", "<br>".join(descs)))
    else:
        rows.append(("Batteries", "<em>none</em>"))

    # Hanging pieces: piece, square, side, type
    hanging = static.get("hanging_pieces", [])
    if hanging:
        descs = []
        for h in hanging[:5]:
            if isinstance(h, dict):
                descs.append(f"{h.get('piece', '?')} ({h.get('type', '?')}) [{h.get('side', '')}]")
            else:
                descs.append(str(h))
        rows.append(("Hanging pieces", "<br>".join(descs)))
    else:
        rows.append(("Hanging pieces", "<em>none</em>"))

    # Trapped pieces
    trapped = static.get("trapped_pieces", [])
    if trapped:
        descs = []
        for t in trapped[:5]:
            if isinstance(t, dict):
                descs.append(f"{t.get('piece', t.get('trapped_piece', '?'))} [{t.get('side', '')}]")
            else:
                descs.append(str(t))
        rows.append(("Trapped pieces", "<br>".join(descs)))
    else:
        rows.append(("Trapped pieces", "<em>none</em>"))

    # X-rays: attacker, through, target, side (key is "xray_attacks")
    xrays = static.get("xray_attacks", []) or static.get("x_rays", [])
    if xrays:
        descs = []
        for x in xrays[:5]:
            if isinstance(x, dict):
                descs.append(
                    f"{x.get('attacker', '?')} through {x.get('through', '?')}"
                    f" → {x.get('target', '?')} [{x.get('side', '')}]"
                )
            else:
                descs.append(str(x))
        rows.append(("X-rays", "<br>".join(descs)))
    else:
        rows.append(("X-rays", "<em>none</em>"))

    # Weak back rank
    back_rank = static.get("weak_back_rank", [])
    if back_rank:
        rows.append(("Weak back rank", ", ".join(str(s) for s in back_rank)))

    return rows


def _fmt_tactics_threats(tac: dict, perspective: str) -> list[tuple[str, str]]:
    """Return list of (threat_name, details_html) for threats.

    Threats are 1-move-away attacks. The move notation (SAN) encodes
    which piece moves to deliver the threat (e.g. Qc8 = queen to c8).
    """
    rows = []
    for threat_key, threat_label in [("threats", perspective), ("opponent_threats", f"opponent of {perspective}")]:
        threats = tac.get(threat_key, {})

        # Forks: move, forking_piece, landing_square, targets (list), side
        forks = threats.get("forks", [])
        if forks:
            descs = []
            for f in forks[:5]:
                if isinstance(f, dict):
                    move = f.get("move", "?")
                    targets = f.get("targets", [])
                    target_str = ", ".join(str(t) for t in targets[:4])
                    descs.append(f"{move} → {target_str}")
                else:
                    descs.append(str(f))
            rows.append((f"Fork threats ({threat_label})", "<br>".join(descs)))

        # Skewers: move, skewering_piece, front_target, rear_target, side
        skewers = threats.get("skewers", [])
        if skewers:
            descs = []
            for s in skewers[:5]:
                if isinstance(s, dict):
                    move = s.get("move", "?")
                    piece = s.get("skewering_piece", "?")
                    front = s.get("front_target", "?")
                    rear = s.get("rear_target", "?")
                    descs.append(f"{move}: {piece} skewers {front} → {rear}")
                else:
                    descs.append(str(s))
            rows.append((f"Skewer threats ({threat_label})", "<br>".join(descs)))

        # Discovered attacks: move, revealed_attacker, target, side
        disc = threats.get("discovered_attacks", [])
        if disc:
            descs = []
            for d in disc[:5]:
                if isinstance(d, dict):
                    move = d.get("move", "?")
                    revealed = d.get("revealed_attacker", d.get("attacker", "?"))
                    target = d.get("target", "?")
                    descs.append(f"{move}: reveals {revealed} → {target}")
                else:
                    descs.append(str(d))
            rows.append((f"Disc. attacks ({threat_label})", "<br>".join(descs)))

        # Checkmate threats: move
        mates = threats.get("checkmate_threats", [])
        if mates:
            descs = []
            for m in mates[:5]:
                if isinstance(m, dict):
                    descs.append(f"{m.get('move', '?')}")
                else:
                    descs.append(str(m))
            rows.append((f"Mate threats ({threat_label})", "<br>".join(descs)))

        # Removal of guard: move, captured_guard, exposed_piece, side
        rog = threats.get("removal_of_guard", [])
        if rog:
            descs = []
            for r in rog[:5]:
                if isinstance(r, dict):
                    descs.append(
                        f"{r.get('move', '?')}: captures {r.get('captured_guard', '?')},"
                        f" exposing {r.get('exposed_piece', '?')}"
                    )
                else:
                    descs.append(str(r))
            rows.append((f"Removal of guard ({threat_label})", "<br>".join(descs)))
    return rows


# ── PV Context ───────────────────────────────────────────────────────────────

def _compute_pv_text(fen: str, analysis: dict, engine_data: dict) -> str | None:
    """Compute PV context text using chess_pipeline logic."""
    try:
        # Import from web backend if available
        from services.chess_pipeline import compute_pv_context
        return compute_pv_context(fen, analysis, engine_data)
    except ImportError:
        pass

    # Fallback: inline computation
    top_lines = engine_data.get("top_lines", [])
    if not top_lines:
        return None

    pv_moves = top_lines[0].get("pv_uci") or top_lines[0].get("pv", [])
    if not pv_moves:
        return None

    try:
        board_pn = chess.Board(fen)
        for uci in pv_moves:
            try:
                move = chess.Move.from_uci(uci)
                if move not in board_pn.legal_moves:
                    raise ValueError
            except (chess.InvalidMoveError, ValueError):
                move = board_pn.parse_san(uci)
            board_pn.push(move)
        analysis_pn = board_utils.analyze_position(board_pn)
    except Exception:
        return None

    vec_p0 = vectorize_stm(analysis)
    vec_pn_raw = vectorize_stm(analysis_pn)

    p0_is_white = analysis.get("side_to_move") == "white"
    pn_is_white = analysis_pn.get("side_to_move") == "white"

    # Perspective alignment
    if p0_is_white != pn_is_white:
        vec_pn = {}
        for k, v in vec_pn_raw.items():
            if k.endswith("_stm"):
                vec_pn[k] = vec_pn_raw.get(k[:-4] + "_opp", 0)
            elif k.endswith("_opp"):
                vec_pn[k] = vec_pn_raw.get(k[:-4] + "_stm", 0)
            elif k in ("material_advantage", "eval_advantage"):
                vec_pn[k] = -v
            else:
                vec_pn[k] = v
    else:
        vec_pn = vec_pn_raw

    # Format PV as SAN
    pv_san = []
    board_tmp = chess.Board(fen)
    for uci in pv_moves:
        try:
            move = chess.Move.from_uci(uci)
            if move not in board_tmp.legal_moves:
                raise ValueError
        except (chess.InvalidMoveError, ValueError):
            move = board_tmp.parse_san(uci)
        pv_san.append(board_tmp.san(move))
        board_tmp.push(move)

    # Build delta text (same tier structure as chess_pipeline.py)
    from services.chess_pipeline import (
        _HUB_FEATURES, _TACTICAL_FEATURES, _BRIDGE_FEATURES,
        _STRUCTURAL_FEATURES, _SKIP_FEATURES, _tier_label, _tier_label_order,
        _format_tactical_motifs,
    )

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
        if isinstance(val_p0, float) or isinstance(val_pn, float):
            tier_deltas[label].append(
                f"  {key:40s}  {val_p0:>7.1f} → {val_pn:>7.1f}  (Δ = {sign}{delta:.1f})"
            )
        else:
            tier_deltas[label].append(
                f"  {key:40s}  {val_p0:>7} → {val_pn:>7}  (Δ = {sign}{delta})"
            )

    stm_color = "White" if p0_is_white else "Black"
    phase = vec_p0.get("game_phase", 0)

    parts = [
        f"\n=== PV ANALYSIS: IMPLICATIVE REASONING DATA ===",
        f"PV ({len(pv_moves)} half-moves): {' '.join(pv_san)}",
        f"PV endpoint FEN: {board_pn.fen()}",
        f"Perspective: {stm_color} (side to move at P₀)",
        f"Game phase: {_phase_name(phase)} ({phase:.2f})",
        "",
    ]

    if tier_deltas:
        parts.append("--- FEATURE DELTAS (P₀ → PV endpoint) ---")
        ordered = sorted(tier_deltas.items(), key=lambda x: _tier_label_order(x[0]))
        for label, lines in ordered:
            parts.append(f"\n{label}:")
            for line in lines:
                parts.append(line)
        parts.append("\n(Only non-zero deltas shown.)")
    else:
        parts.append("No significant feature changes detected along this PV.")

    parts.append("")
    parts.append("--- TACTICAL MOTIFS AT CURRENT POSITION (P₀) ---")
    parts.append(_format_tactical_motifs(analysis, stm_color))
    parts.append("")
    parts.append("--- TACTICAL MOTIFS AT PV ENDPOINT (P_n) ---")
    opp_color = "Black" if stm_color == "White" else "White"
    pn_perspective = stm_color if p0_is_white == pn_is_white else opp_color
    parts.append(_format_tactical_motifs(analysis_pn, pn_perspective))

    return "\n".join(parts)


# ── HTML generation ──────────────────────────────────────────────────────────

_CSS = """
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Georgia', serif; background: #f5f0eb; color: #2c2c2c; line-height: 1.6; }
  .container { max-width: 1400px; margin: 0 auto; padding: 24px; }

  h1 { font-size: 1.8em; margin-bottom: 4px; color: #1a1a1a; }
  h2 { font-size: 1.3em; margin: 24px 0 12px; color: #333; border-bottom: 2px solid #c9a96e; padding-bottom: 4px; }
  h3 { font-size: 1.1em; margin: 16px 0 8px; color: #555; }
  .subtitle { font-size: 1.1em; color: #666; margin-bottom: 20px; font-style: italic; }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }
  .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 24px; }

  .card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  .card-accent { border-left: 4px solid #c9a96e; }
  .card-blue { border-left: 4px solid #4a7ab5; }
  .card-green { border-left: 4px solid #5a9e6f; }
  .card-red { border-left: 4px solid #c0392b; }
  .card-purple { border-left: 4px solid #8e44ad; }

  .board-container { text-align: center; }
  .board-container svg { max-width: 100%; height: auto; border-radius: 4px; box-shadow: 0 4px 16px rgba(0,0,0,0.15); }

  table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
  th, td { padding: 6px 10px; text-align: left; border-bottom: 1px solid #e5e0da; }
  th { background: #f0ebe5; font-weight: 600; }
  tr:hover { background: #faf8f5; }

  .feature-row { display: flex; justify-content: space-between; padding: 3px 0; font-size: 0.88em; }
  .feature-label { color: #555; }
  .feature-val { font-weight: 600; font-family: monospace; }
  .positive { color: #27ae60; }
  .negative { color: #c0392b; }
  .neutral { color: #777; }

  pre { background: #2d2d2d; color: #e8e8e8; padding: 16px; border-radius: 6px; overflow-x: auto;
         font-size: 0.82em; line-height: 1.5; white-space: pre-wrap; }
  code { font-family: 'Fira Code', 'Consolas', monospace; }

  .guide-section { background: white; border-radius: 8px; padding: 28px; box-shadow: 0 2px 12px rgba(0,0,0,0.1);
                     line-height: 1.75; font-size: 1.02em; }
  .guide-section p { margin-bottom: 14px; }
  .guide-section strong { color: #1a1a1a; }

  .tag { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 0.78em; font-weight: 600; margin-right: 4px; }
  .tag-hub { background: #e8f4fd; color: #2980b9; }
  .tag-tactical { background: #fde8e8; color: #c0392b; }
  .tag-bridge { background: #e8fde8; color: #27ae60; }
  .tag-creation { background: #fff3e0; color: #e67e22; }
  .tag-elimination { background: #e8f5e9; color: #2e7d32; }

  .meta { font-size: 0.85em; color: #888; margin-top: 20px; }
  .gm-quote { border-left: 3px solid #c9a96e; padding-left: 16px; margin: 12px 0; font-style: italic; color: #444; }
  .undeveloped { display: inline-block; padding: 1px 6px; background: #fde8e8; border-radius: 3px; font-size: 0.85em; color: #c0392b; }

  @media print {
    body { background: white; }
    .card { box-shadow: none; border: 1px solid #ddd; }
    pre { background: #f5f5f5; color: #333; }
  }
"""


def generate_playbook_html(
    fen: str,
    *,
    depth: int = 22,
    lines: int = 3,
    title: str | None = None,
    subtitle: str | None = None,
    guide_html: str | None = None,
    output_path: Path | str | None = None,
) -> str:
    """Generate a complete HTML Player's Guide document for a position.

    Parameters
    ----------
    fen : str
        FEN string of the position to analyze.
    depth : int
        Stockfish search depth.
    lines : int
        Number of multi-PV lines.
    title : str, optional
        Custom title (default: auto-generated from FEN).
    subtitle : str, optional
        Custom subtitle line.
    guide_html : str, optional
        Pre-written Player's Guide narrative as HTML. If omitted, a
        placeholder section is emitted.
    output_path : Path or str, optional
        If provided, write HTML to this file.

    Returns
    -------
    str
        The complete HTML document.
    """
    board = chess.Board(fen)

    # ── Run analysis pipeline ────────────────────────────────────────────
    with EngineEval() as engine:
        analysis = board_utils.analyze_position(board, engine=engine,
                                                 engine_depth=depth,
                                                 engine_lines=lines)
        multi = engine.evaluate_multipv(board, num_lines=lines, depth=depth)
        single = multi[0] if multi else None

    engine_data = {"eval": single, "top_lines": multi}

    # Board SVG (inline)
    last_move = None
    if board.move_stack:
        last_move = board.peek()
    board_svg = chess.svg.board(board, lastmove=last_move, size=450)

    # ── Extract data ─────────────────────────────────────────────────────
    mat = analysis.get("material", {})
    dev = analysis.get("development", {})
    init = analysis.get("initiative", {})
    space = analysis.get("space", {})
    ks_w = analysis.get("king_safety", {}).get("white", {})
    ks_b = analysis.get("king_safety", {}).get("black", {})
    tac = analysis.get("tactics", {})
    phase_raw = analysis.get("game_phase", {}).get("phase", 0.0)
    # Phase can be a string label or float — normalize to float
    if isinstance(phase_raw, str):
        phase_val = {"opening": 0.1, "middlegame": 0.5, "endgame": 0.9}.get(phase_raw.lower(), 0.5)
    else:
        phase_val = float(phase_raw)
    total_npm = analysis.get("game_phase", {}).get("total_non_pawn_material", 0)
    stm = analysis.get("side_to_move", "white")
    stm_color = "White" if stm == "white" else "Black"

    # Engine top line
    eval_score = single.get("score_display", "0.00") if single else "0.00"
    eval_cp = single.get("score_cp") if single else 0
    if eval_cp is None:
        # Mate score — use mate_in to determine sign
        mate_in = single.get("mate_in", 0) if single else 0
        eval_float = 100.0 if mate_in and mate_in > 0 else -100.0 if mate_in else 0.0
    else:
        eval_float = eval_cp / 100.0

    # ── PV context ───────────────────────────────────────────────────────
    pv_context = _compute_pv_text(fen, analysis, engine_data)

    # ── Build HTML ───────────────────────────────────────────────────────
    if title is None:
        title = "Implicative Reasoning Playbook: Player's Guide"
    if subtitle is None:
        move_num = board.fullmove_number
        subtitle = f"Position: {stm_color} to move (move {move_num})"

    h = []
    h.append("<!DOCTYPE html>")
    h.append('<html lang="en">')
    h.append("<head>")
    h.append('<meta charset="UTF-8">')
    h.append(f"<title>{html.escape(title)}</title>")
    h.append(f"<style>{_CSS}</style>")
    h.append("</head>")
    h.append("<body>")
    h.append('<div class="container">')
    h.append(f"<h1>{html.escape(title)}</h1>")
    h.append(f'<div class="subtitle">{html.escape(subtitle)}</div>')

    # Row 1: Board + Engine
    h.append('<div class="grid">')
    h.append('  <div class="card board-container">')
    h.append(f'    <h2>Position ({stm_color} to move, Move {board.fullmove_number})</h2>')
    h.append(f"    {board_svg}")
    h.append(f'    <p style="margin-top:8px; font-size:0.85em; color:#666;"><code>{html.escape(fen)}</code></p>')
    h.append("  </div>")
    h.append('  <div class="card card-accent">')
    h.append(f"    <h2>Engine Evaluation (Stockfish depth {depth})</h2>")
    h.append(f'    <div style="font-size: 2.2em; font-weight: bold; color: {_eval_color(eval_float)}; margin: 8px 0;">')
    h.append(f"      {html.escape(str(eval_score))}")
    h.append("    </div>")
    h.append(f'    <p style="color:#666; margin-bottom:16px;">{_eval_description(eval_float)}</p>')

    # Top lines table
    h.append("    <h3>Top Lines</h3>")
    h.append("    <table>")
    h.append("      <tr><th>#</th><th>Eval</th><th>Principal Variation</th></tr>")
    for i, line in enumerate(multi or [], 1):
        score_disp = line.get("score_display", "?")
        pv = line.get("pv", [])
        pv_str = " ".join(pv[:8])
        h.append(f'      <tr><td>{i}</td><td><strong>{html.escape(str(score_disp))}</strong></td><td><code>{html.escape(pv_str)}</code></td></tr>')
    h.append("    </table>")

    # Best move description
    if single and single.get("best_move"):
        best = single["best_move"]
        h.append(f'    <h3 style="margin-top:16px;">Engine\'s Recommendation</h3>')
        h.append(f"    <p><strong>{html.escape(best)}</strong></p>")
    h.append("  </div>")
    h.append("</div>")

    # Row 2: Imbalances (3-column)
    w_mat_pts = mat.get("white", {}).get("total_points", 0)
    b_mat_pts = mat.get("black", {}).get("total_points", 0)
    mat_balance = w_mat_pts - b_mat_pts
    bal_class = "positive" if mat_balance > 0 else "negative" if mat_balance < 0 else "neutral"

    h.append('<div class="grid-3">')

    # Material card
    h.append('  <div class="card card-blue">')
    h.append("    <h2>Material</h2>")
    h.append(f'    <div class="feature-row"><span class="feature-label">White total</span><span class="feature-val">{w_mat_pts} pts</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">Black total</span><span class="feature-val">{b_mat_pts} pts</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">Balance</span><span class="feature-val {bal_class}">{mat_balance:+d} pts</span></div>')
    h.append('    <hr style="margin:10px 0; border-color:#eee;">')
    h.append(f'    <div class="feature-row"><span class="feature-label">White</span><span class="feature-val">{_fmt_pieces(mat, "white")}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">Black</span><span class="feature-val">{_fmt_pieces(mat, "black")}</span></div>')
    h.append('    <hr style="margin:10px 0; border-color:#eee;">')
    h.append(f'    <div class="feature-row"><span class="feature-label">Game Phase</span><span class="feature-val">{_phase_name(phase_val)}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">Non-pawn material</span><span class="feature-val">{total_npm}</span></div>')
    h.append("  </div>")

    # Development & Initiative card
    w_dev = dev.get("white", {}).get("development_count", 0)
    w_dev_total = dev.get("white", {}).get("total_developable", 0)
    b_dev = dev.get("black", {}).get("development_count", 0)
    b_dev_total = dev.get("black", {}).get("total_developable", 0)
    w_init = init.get("white", {}).get("initiative_score", 0)
    b_init = init.get("black", {}).get("initiative_score", 0)
    w_checks = init.get("white", {}).get("checks_available", 0)
    b_checks = init.get("black", {}).get("checks_available", 0)
    w_captures = init.get("white", {}).get("captures_available", 0)
    b_captures = init.get("black", {}).get("captures_available", 0)
    w_space = space.get("white", {}).get("squares_controlled_in_enemy_half", 0)
    b_space = space.get("black", {}).get("squares_controlled_in_enemy_half", 0)

    h.append('  <div class="card card-green">')
    h.append("    <h2>Development & Initiative</h2>")
    dev_w_class = "positive" if w_dev >= b_dev else ""
    dev_b_class = "negative" if b_dev < w_dev else ""
    h.append(f'    <div class="feature-row"><span class="feature-label">White developed</span><span class="feature-val {dev_w_class}">{w_dev}/{w_dev_total}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">Black developed</span><span class="feature-val {dev_b_class}">{b_dev}/{b_dev_total}</span></div>')
    w_undev = _fmt_undeveloped(dev, "white")
    b_undev = _fmt_undeveloped(dev, "black")
    h.append(f'    <div class="feature-row"><span class="feature-label">W undeveloped</span><span class="feature-val">{html.escape(w_undev)}</span></div>')
    if b_undev != "—":
        h.append(f'    <div class="feature-row"><span class="feature-label">B undeveloped</span><span class="feature-val"><span class="undeveloped">{html.escape(b_undev)}</span></span></div>')
    else:
        h.append(f'    <div class="feature-row"><span class="feature-label">B undeveloped</span><span class="feature-val">{html.escape(b_undev)}</span></div>')
    h.append('    <hr style="margin:10px 0; border-color:#eee;">')
    init_w_class = "positive" if w_init > b_init else ""
    h.append(f'    <div class="feature-row"><span class="feature-label">Initiative (W)</span><span class="feature-val {init_w_class}">{w_init}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">Initiative (B)</span><span class="feature-val">{b_init}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">Checks avail (W)</span><span class="feature-val">{w_checks}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">Checks avail (B)</span><span class="feature-val">{b_checks}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">Captures avail (W)</span><span class="feature-val">{w_captures}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">Captures avail (B)</span><span class="feature-val">{b_captures}</span></div>')
    h.append('    <hr style="margin:10px 0; border-color:#eee;">')
    space_w_class = "positive" if w_space > b_space else ""
    h.append(f'    <div class="feature-row"><span class="feature-label">Space (W)</span><span class="feature-val {space_w_class}">{w_space} squares</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">Space (B)</span><span class="feature-val">{b_space} squares</span></div>')
    h.append("  </div>")

    # King Safety card
    w_king_sq = ks_w.get("king_square", "?")
    b_king_sq = ks_b.get("king_square", "?")

    h.append('  <div class="card card-red">')
    h.append("    <h2>King Safety</h2>")
    h.append(f'    <div class="feature-row"><span class="feature-label">W king</span><span class="feature-val">{w_king_sq}</span></div>')
    w_castled_str = _fmt_castling(ks_w)
    castled_class = "positive" if ks_w.get("has_castled") else ""
    h.append(f'    <div class="feature-row"><span class="feature-label">W castled</span><span class="feature-val {castled_class}">{html.escape(w_castled_str)}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">W pawn shield</span><span class="feature-val">{_fmt_shield(ks_w.get("pawn_shield"))}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">W attackers nearby</span><span class="feature-val">{_fmt_attackers(ks_w.get("nearby_attackers"))}</span></div>')
    h.append('    <hr style="margin:10px 0; border-color:#eee;">')
    b_castled_str = _fmt_castling(ks_b)
    b_castled_class = "negative" if not ks_b.get("has_castled") else "positive"
    h.append(f'    <div class="feature-row"><span class="feature-label">B king</span><span class="feature-val {b_castled_class}">{b_king_sq}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">B castled</span><span class="feature-val {b_castled_class}">{html.escape(b_castled_str)}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">B pawn shield</span><span class="feature-val">{_fmt_shield(ks_b.get("pawn_shield"))}</span></div>')
    h.append(f'    <div class="feature-row"><span class="feature-label">B attackers nearby</span><span class="feature-val">{_fmt_attackers(ks_b.get("nearby_attackers"))}</span></div>')
    h.append('    <hr style="margin:10px 0; border-color:#eee;">')
    mate = tac.get("threats", {}).get("checkmate_threats", [])
    mate_str = f"{len(mate)} threat(s)" if mate else "None"
    h.append(f'    <div class="feature-row"><span class="feature-label">Mate threat</span><span class="feature-val">{mate_str}</span></div>')
    h.append("  </div>")
    h.append("</div>")

    # Row 3: Tactical Motifs
    h.append('<div class="card card-purple" style="margin-bottom:24px;">')
    h.append("  <h2>Tactical Motifs</h2>")
    h.append('  <div class="grid">')

    # Static patterns
    h.append("    <div>")
    h.append("      <h3>Static Patterns</h3>")
    h.append("      <table>")
    h.append("        <tr><th>Pattern</th><th>Details</th></tr>")
    for label, details in _fmt_tactics_static(tac):
        h.append(f"        <tr><td>{label}</td><td>{details}</td></tr>")
    h.append("      </table>")
    h.append("    </div>")

    # Threats
    h.append("    <div>")
    h.append("      <h3>Threats</h3>")
    h.append("      <table>")
    h.append("        <tr><th>Threat</th><th>Details</th></tr>")
    for label, details in _fmt_tactics_threats(tac, stm_color):
        h.append(f"        <tr><td>{label}</td><td>{details}</td></tr>")
    h.append("      </table>")
    h.append("    </div>")

    h.append("  </div>")
    h.append("</div>")

    # Row 4: PV Feature Deltas
    if pv_context:
        pv_san_display = ""
        if multi:
            pv = multi[0].get("pv", [])
            pv_san_display = " ".join(pv[:10])
        h.append('<div class="card card-accent" style="margin-bottom:24px;">')
        h.append("  <h2>PV Feature Deltas — Implicative Reasoning</h2>")
        h.append(f'  <p style="color:#666; font-size:0.9em; margin-bottom:12px;">Feature changes from current position (P₀) to PV endpoint (P_n) after <strong>{html.escape(pv_san_display)}</strong></p>')
        h.append(f"  <pre>{html.escape(pv_context)}</pre>")
        h.append("</div>")

    # Row 5: Player's Guide
    if guide_html:
        h.append('<div class="guide-section card-accent" style="border-left: 4px solid #c9a96e; margin-bottom:24px;">')
        h.append('  <h2 style="color:#8b6914;">Player\'s Guide — Implicative Reasoning Playbook</h2>')
        h.append(guide_html)
        h.append("</div>")
    else:
        h.append('<div class="guide-section card-accent" style="border-left: 4px solid #c9a96e; margin-bottom:24px;">')
        h.append('  <h2 style="color:#8b6914;">Player\'s Guide — Implicative Reasoning Playbook</h2>')
        h.append("  <p><em>Guide narrative not provided. Use --guide-text to inject a pre-written guide, or generate one via the web app.</em></p>")
        h.append("</div>")

    # Footer
    h.append('<div class="meta" style="margin-top: 24px; text-align: center;">')
    h.append(f"  <p>Generated by the Implicative Reasoning Playbook — Stockfish depth {depth}, 74-feature precision matrix</p>")
    h.append("  <p>Analysis pipeline: board_utils.py → tactical_motifs.py → engine_eval.py → imbalance_vectorizer.py → compute_pv_context()</p>")
    h.append("</div>")

    h.append("</div>")
    h.append("</body>")
    h.append("</html>")

    result = "\n".join(h)

    if output_path:
        output_path = Path(output_path)
        output_path.write_text(result, encoding="utf-8")

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate HTML Player's Guide for a chess position")
    parser.add_argument("fen", help="FEN string of the position")
    parser.add_argument("--depth", type=int, default=22, help="Stockfish depth (default: 22)")
    parser.add_argument("--lines", type=int, default=3, help="Number of PV lines (default: 3)")
    parser.add_argument("--title", help="Custom title")
    parser.add_argument("--subtitle", help="Custom subtitle")
    parser.add_argument("--output", "-o", help="Output HTML file path")
    parser.add_argument("--guide-text", help="Path to a file containing the Player's Guide HTML")
    parser.add_argument("--open", action="store_true", help="Open result in Chrome")
    args = parser.parse_args()

    guide_html = None
    if args.guide_text:
        guide_html = Path(args.guide_text).read_text(encoding="utf-8")

    output = args.output or "playbook.html"

    print(f"Analyzing position: {args.fen}")
    print(f"Depth: {args.depth}, Lines: {args.lines}")

    result = generate_playbook_html(
        args.fen,
        depth=args.depth,
        lines=args.lines,
        title=args.title,
        subtitle=args.subtitle,
        guide_html=guide_html,
        output_path=output,
    )

    print(f"Wrote {len(result):,} chars → {output}")

    if args.open:
        subprocess.Popen(["xdg-open", output])


if __name__ == "__main__":
    main()
