"""Vectorize board_utils analysis JSON into flat numerical features.

Two representations:
- Absolute (white/black): vectorize() → FEATURE_NAMES
- Side-to-move relative: vectorize_stm() → STM_FEATURE_NAMES
  Features expressed as stm/opp (color-agnostic), with eval_advantage column.
  Enables universal move archetypes that don't depend on playing color.

Usage:
    from imbalance_vectorizer import vectorize, vectorize_stm, compute_deltas
    features = vectorize(analyze_position(board))
    stm_features = vectorize_stm(analyze_position(board))
    deltas = compute_deltas(features_before, features_after)
"""

from __future__ import annotations


# Ordered list of feature names — defines the canonical feature vector.
FEATURE_NAMES: list[str] = [
    # ── Material (Silman #1) ─────────────────────────────────────
    "material_balance",         # white_total - black_total (centipawns)
    "bishop_pair_advantage",    # +1 white only, -1 black only, 0 both/neither
    "queen_count_white",
    "queen_count_black",
    "rook_count_white",
    "rook_count_black",
    "minor_count_white",        # knights + bishops
    "minor_count_black",
    "pawn_count_white",
    "pawn_count_black",

    # ── Pawn Structure (Silman #2 minor, #3 passed pawns) ────────
    "passed_pawns_white",
    "passed_pawns_black",
    "doubled_pawns_white",
    "doubled_pawns_black",
    "isolated_pawns_white",
    "isolated_pawns_black",
    "backward_pawns_white",
    "backward_pawns_black",
    "pawn_islands_white",
    "pawn_islands_black",

    # ── Piece Activity (Silman #4 — piece mobility) ──────────────
    "squares_attacked_white",
    "squares_attacked_black",
    "center_control_white",     # count of central squares controlled
    "center_control_black",
    "knight_outposts_white",
    "knight_outposts_black",
    "rooks_on_open_files_white",
    "rooks_on_open_files_black",
    "rooks_on_7th_white",
    "rooks_on_7th_black",

    # ── Files (Silman #5) ────────────────────────────────────────
    "open_files",
    "semi_open_files_white",
    "semi_open_files_black",

    # ── King Safety (Silman #6) ──────────────────────────────────
    "pawn_shield_white",
    "pawn_shield_black",
    "missing_shield_white",
    "missing_shield_black",
    "king_attackers_white",     # count of enemy pieces near white king
    "king_attackers_black",
    "castling_rights_white",    # 0, 1, or 2
    "castling_rights_black",
    "mate_threat_exists",       # 1 if any side has mate threat

    # ── Space (Silman #7) ────────────────────────────────────────
    "space_white",
    "space_black",

    # ── Development (Silman #8) ──────────────────────────────────
    "development_white",
    "development_black",

    # ── Superior Minor Piece (Silman #9) ─────────────────────────
    "minor_piece_score_white",
    "minor_piece_score_black",
    "bad_bishops_white",
    "bad_bishops_black",

    # ── Initiative (Silman #10) ──────────────────────────────────
    "initiative_score_white",
    "initiative_score_black",
    "checks_available_white",
    "checks_available_black",

    # ── Statics vs Dynamics (composite) ──────────────────────────
    "static_score_white",
    "static_score_black",
    "dynamic_score_white",
    "dynamic_score_black",

    # ── Tactical motif counts ────────────────────────────────────
    "pin_count",
    "battery_count",
    "hanging_pieces_count",
    "trapped_pieces_count",
    "fork_threats_white",
    "fork_threats_black",
    "skewer_threats_white",
    "skewer_threats_black",
    "discovered_attack_threats_white",
    "discovered_attack_threats_black",
    "checkmate_threats_white",
    "checkmate_threats_black",

    # ── Game phase & position flags ──────────────────────────────
    "game_phase",               # 0=opening, 1=middlegame, 2=endgame
    "total_non_pawn_material",
    "is_check",
    "side_to_move",             # 1=white, 0=black
]


_PHASE_MAP = {
    "opening": 0,
    "middlegame": 1,
    "early_endgame": 2,
    "endgame": 2,
}


def _count_by_side(items: list[dict], side: str) -> int:
    """Count tactical motif entries belonging to a specific side."""
    return sum(1 for item in items if item.get("side") == side)


def vectorize(analysis: dict) -> dict[str, int | float]:
    """Convert an analyze_position() result dict into a flat feature vector.

    Args:
        analysis: Output of board_utils.analyze_position(board).

    Returns:
        Dict mapping feature name → numeric value, with keys matching FEATURE_NAMES.
    """
    mat = analysis.get("material", {})
    mat_w = mat.get("white", {})
    mat_b = mat.get("black", {})

    ps = analysis.get("pawn_structure", {})
    ps_w = ps.get("white", {})
    ps_b = ps.get("black", {})

    pa = analysis.get("piece_activity", {})
    pa_w = pa.get("white", {})
    pa_b = pa.get("black", {})

    files = analysis.get("files", {})

    ks = analysis.get("king_safety", {})
    ks_w = ks.get("white", {})
    ks_b = ks.get("black", {})

    sp = analysis.get("space", {})
    sp_w = sp.get("white", {})
    sp_b = sp.get("black", {})

    dev = analysis.get("development", {})
    dev_w = dev.get("white", {})
    dev_b = dev.get("black", {})

    smp = analysis.get("superior_minor_piece", {})
    smp_w = smp.get("white", {})
    smp_b = smp.get("black", {})

    init = analysis.get("initiative", {})
    init_w = init.get("white", {})
    init_b = init.get("black", {})

    svd = analysis.get("statics_vs_dynamics", {})
    svd_w = svd.get("white", {})
    svd_b = svd.get("black", {})

    tac = analysis.get("tactics", {})
    tac_static = tac.get("static", {})
    tac_threats = tac.get("threats", {})
    tac_opp_threats = tac.get("opponent_threats", {})

    gp = analysis.get("game_phase", {})

    # Bishop pair advantage
    bp_w = mat_w.get("bishop_pair", False)
    bp_b = mat_b.get("bishop_pair", False)
    if bp_w and not bp_b:
        bishop_pair_adv = 1
    elif bp_b and not bp_w:
        bishop_pair_adv = -1
    else:
        bishop_pair_adv = 0

    # Castling rights
    cr_w = int(ks_w.get("can_castle_kingside", False)) + int(ks_w.get("can_castle_queenside", False))
    cr_b = int(ks_b.get("can_castle_kingside", False)) + int(ks_b.get("can_castle_queenside", False))

    # Mate threat
    mate_w = ks_w.get("mate_threat") is not None
    mate_b = ks_b.get("mate_threat") is not None

    # Tactical counts — per-side for threats
    # Merge STM threats + opponent threats for complete per-side counts
    forks = tac_threats.get("forks", []) + tac_opp_threats.get("forks", [])
    skewers = tac_threats.get("skewers", [])  # skewers not in opponent_threats
    disc_attacks = (tac_threats.get("discovered_attacks", [])
                    + tac_opp_threats.get("discovered_attacks", []))
    cm_threats = (tac_threats.get("checkmate_threats", [])
                  + tac_opp_threats.get("checkmate_threats", []))

    return {
        # Material
        "material_balance": mat.get("balance", 0),
        "bishop_pair_advantage": bishop_pair_adv,
        "queen_count_white": mat_w.get("queens", 0),
        "queen_count_black": mat_b.get("queens", 0),
        "rook_count_white": mat_w.get("rooks", 0),
        "rook_count_black": mat_b.get("rooks", 0),
        "minor_count_white": mat_w.get("knights", 0) + mat_w.get("bishops", 0),
        "minor_count_black": mat_b.get("knights", 0) + mat_b.get("bishops", 0),
        "pawn_count_white": mat_w.get("pawns", 0),
        "pawn_count_black": mat_b.get("pawns", 0),

        # Pawn structure
        "passed_pawns_white": len(ps_w.get("passed", [])),
        "passed_pawns_black": len(ps_b.get("passed", [])),
        "doubled_pawns_white": len(ps_w.get("doubled", [])),
        "doubled_pawns_black": len(ps_b.get("doubled", [])),
        "isolated_pawns_white": len(ps_w.get("isolated", [])),
        "isolated_pawns_black": len(ps_b.get("isolated", [])),
        "backward_pawns_white": len(ps_w.get("backward", [])),
        "backward_pawns_black": len(ps_b.get("backward", [])),
        "pawn_islands_white": ps_w.get("pawn_islands", 0),
        "pawn_islands_black": ps_b.get("pawn_islands", 0),

        # Piece activity
        "squares_attacked_white": pa_w.get("squares_attacked", 0),
        "squares_attacked_black": pa_b.get("squares_attacked", 0),
        "center_control_white": len(pa_w.get("center_control", [])),
        "center_control_black": len(pa_b.get("center_control", [])),
        "knight_outposts_white": len(pa_w.get("knight_outposts", [])),
        "knight_outposts_black": len(pa_b.get("knight_outposts", [])),
        "rooks_on_open_files_white": len(pa_w.get("rooks_on_open_files", [])),
        "rooks_on_open_files_black": len(pa_b.get("rooks_on_open_files", [])),
        "rooks_on_7th_white": len(pa_w.get("rooks_on_7th_rank", [])),
        "rooks_on_7th_black": len(pa_b.get("rooks_on_7th_rank", [])),

        # Files
        "open_files": len(files.get("open", [])),
        "semi_open_files_white": len(files.get("white_semi_open", [])),
        "semi_open_files_black": len(files.get("black_semi_open", [])),

        # King safety
        "pawn_shield_white": len(ks_w.get("pawn_shield", [])),
        "pawn_shield_black": len(ks_b.get("pawn_shield", [])),
        "missing_shield_white": len(ks_w.get("missing_shield", [])),
        "missing_shield_black": len(ks_b.get("missing_shield", [])),
        "king_attackers_white": len(ks_w.get("nearby_attackers", [])),
        "king_attackers_black": len(ks_b.get("nearby_attackers", [])),
        "castling_rights_white": cr_w,
        "castling_rights_black": cr_b,
        "mate_threat_exists": int(mate_w or mate_b),

        # Space
        "space_white": sp_w.get("squares_controlled_in_enemy_half", 0),
        "space_black": sp_b.get("squares_controlled_in_enemy_half", 0),

        # Development
        "development_white": dev_w.get("development_count", 0),
        "development_black": dev_b.get("development_count", 0),

        # Superior minor piece
        "minor_piece_score_white": smp_w.get("minor_piece_score", 0),
        "minor_piece_score_black": smp_b.get("minor_piece_score", 0),
        "bad_bishops_white": len(smp_w.get("bad_bishops", [])),
        "bad_bishops_black": len(smp_b.get("bad_bishops", [])),

        # Initiative
        "initiative_score_white": init_w.get("initiative_score", 0),
        "initiative_score_black": init_b.get("initiative_score", 0),
        "checks_available_white": init_w.get("checks_available", 0),
        "checks_available_black": init_b.get("checks_available", 0),

        # Statics vs dynamics
        "static_score_white": svd_w.get("static_score", 0),
        "static_score_black": svd_b.get("static_score", 0),
        "dynamic_score_white": svd_w.get("dynamic_score", 0),
        "dynamic_score_black": svd_b.get("dynamic_score", 0),

        # Tactical counts
        "pin_count": len(tac_static.get("pins", [])),
        "battery_count": len(tac_static.get("batteries", [])),
        "hanging_pieces_count": len(tac_static.get("hanging_pieces", [])),
        "trapped_pieces_count": len(tac_static.get("trapped_pieces", [])),
        "fork_threats_white": _count_by_side(forks, "white"),
        "fork_threats_black": _count_by_side(forks, "black"),
        "skewer_threats_white": _count_by_side(skewers, "white"),
        "skewer_threats_black": _count_by_side(skewers, "black"),
        "discovered_attack_threats_white": _count_by_side(disc_attacks, "white"),
        "discovered_attack_threats_black": _count_by_side(disc_attacks, "black"),
        "checkmate_threats_white": _count_by_side(cm_threats, "white"),
        "checkmate_threats_black": _count_by_side(cm_threats, "black"),

        # Game phase & flags
        "game_phase": _PHASE_MAP.get(gp.get("phase", "middlegame"), 1),
        "total_non_pawn_material": gp.get("total_non_pawn_material", 0),
        "is_check": int(analysis.get("is_check", False)),
        "side_to_move": 1 if analysis.get("side_to_move") == "white" else 0,
    }


# ── Side-to-move relative feature schema ─────────────────────────────────
# Features expressed as stm (side to move) / opp (opponent).
# eval_advantage = engine eval from STM perspective (positive = STM is ahead).

STM_FEATURE_NAMES: list[str] = [
    # ── Material ─────────────────────────────────────────────────
    "material_advantage",       # stm_total - opp_total (centipawns)
    "bishop_pair_stm",          # 1 if stm has bishop pair, else 0
    "bishop_pair_opp",
    "queen_count_stm",
    "queen_count_opp",
    "rook_count_stm",
    "rook_count_opp",
    "minor_count_stm",
    "minor_count_opp",
    "pawn_count_stm",
    "pawn_count_opp",

    # ── Pawn Structure ───────────────────────────────────────────
    "passed_pawns_stm",
    "passed_pawns_opp",
    "doubled_pawns_stm",
    "doubled_pawns_opp",
    "isolated_pawns_stm",
    "isolated_pawns_opp",
    "backward_pawns_stm",
    "backward_pawns_opp",
    "pawn_islands_stm",
    "pawn_islands_opp",

    # ── Piece Activity ───────────────────────────────────────────
    "squares_attacked_stm",
    "squares_attacked_opp",
    "center_control_stm",
    "center_control_opp",
    "knight_outposts_stm",
    "knight_outposts_opp",
    "rooks_on_open_files_stm",
    "rooks_on_open_files_opp",
    "rooks_on_7th_stm",
    "rooks_on_7th_opp",

    # ── Files ────────────────────────────────────────────────────
    "open_files",
    "semi_open_files_stm",
    "semi_open_files_opp",

    # ── King Safety ──────────────────────────────────────────────
    "pawn_shield_stm",
    "pawn_shield_opp",
    "missing_shield_stm",
    "missing_shield_opp",
    "king_attackers_stm",       # enemy pieces near STM's king
    "king_attackers_opp",       # STM's pieces near opponent's king
    "castling_rights_stm",
    "castling_rights_opp",
    "mate_threat_by_stm",       # 1 if STM has mate threat
    "mate_threat_by_opp",       # 1 if opponent has mate threat

    # ── Space ────────────────────────────────────────────────────
    "space_stm",
    "space_opp",

    # ── Development ──────────────────────────────────────────────
    "development_stm",
    "development_opp",

    # ── Superior Minor Piece ─────────────────────────────────────
    "minor_piece_score_stm",
    "minor_piece_score_opp",
    "bad_bishops_stm",
    "bad_bishops_opp",

    # ── Initiative ───────────────────────────────────────────────
    "initiative_score_stm",
    "initiative_score_opp",
    "checks_available_stm",
    "checks_available_opp",

    # ── Statics vs Dynamics ──────────────────────────────────────
    "static_score_stm",
    "static_score_opp",
    "dynamic_score_stm",
    "dynamic_score_opp",

    # ── Tactical motif counts ────────────────────────────────────
    "pin_count",
    "battery_count",
    "hanging_pieces_count",
    "trapped_pieces_count",
    "fork_threats_stm",
    "fork_threats_opp",
    "skewer_threats_stm",
    "skewer_threats_opp",
    "discovered_attack_threats_stm",
    "discovered_attack_threats_opp",
    "checkmate_threats_stm",
    "checkmate_threats_opp",

    # ── Spatial context (STM-relative) ────────────────────────────
    "region_center",            # center region control: stm(+1), neutral(0), opp(-1)
    "region_stm_kingside",      # STM's kingside corner control
    "region_stm_queenside",     # STM's queenside corner control
    "region_opp_kingside",      # OPP's kingside corner control
    "region_opp_queenside",     # OPP's queenside corner control
    "stm_king_file",            # queenside(-1), center(0), kingside(+1)
    "stm_king_rank",            # advanced(-1), center(0), home(+1)
    "opp_king_file",            # queenside(-1), center(0), kingside(+1)
    "opp_king_rank",            # advanced(-1), center(0), home(+1)

    # ── Game phase & context ─────────────────────────────────────
    "game_phase",
    "total_non_pawn_material",
    "is_check",
    "eval_advantage",           # engine eval from STM perspective (positive = ahead)
]


def _compute_spatial_features(analysis: dict, is_white: bool) -> dict[str, int]:
    """Compute 9 spatial context features (STM-relative).

    5 regional control nodes + 4 king location nodes.
    All values are ternary: -1, 0, or +1.
    """
    rc = analysis.get("regional_control", {})
    regions = rc.get("regions", {})
    king_locs = rc.get("king_locations", {})

    if is_white:
        # White is STM: white's home corners = STM corners, black's = OPP
        # Region control values are already +1=white, -1=black from board_utils
        # So for White STM: +1=stm, -1=opp → keep as-is
        center = regions.get("center", 0)
        stm_ks = regions.get("white_kingside", 0)
        stm_qs = regions.get("white_queenside", 0)
        opp_ks = regions.get("black_kingside", 0)
        opp_qs = regions.get("black_queenside", 0)
        # King locations: already from white/black perspective in board_utils
        stm_kf = king_locs.get("white_king_file", 0)
        stm_kr = king_locs.get("white_king_rank", 0)
        opp_kf = king_locs.get("black_king_file", 0)
        opp_kr = king_locs.get("black_king_rank", 0)
    else:
        # Black is STM: black's home corners = STM corners, white's = OPP
        # Region control: flip sign (black control = +1 for STM)
        center = -regions.get("center", 0)
        stm_ks = -regions.get("black_kingside", 0)
        stm_qs = -regions.get("black_queenside", 0)
        opp_ks = -regions.get("white_kingside", 0)
        opp_qs = -regions.get("white_queenside", 0)
        # King locations: swap white/black and flip rank
        stm_kf = king_locs.get("black_king_file", 0)
        stm_kr = king_locs.get("black_king_rank", 0)
        opp_kf = king_locs.get("white_king_file", 0)
        opp_kr = king_locs.get("white_king_rank", 0)

    return {
        "region_center": center,
        "region_stm_kingside": stm_ks,
        "region_stm_queenside": stm_qs,
        "region_opp_kingside": opp_ks,
        "region_opp_queenside": opp_qs,
        "stm_king_file": stm_kf,
        "stm_king_rank": stm_kr,
        "opp_king_file": opp_kf,
        "opp_king_rank": opp_kr,
    }


def vectorize_stm(analysis: dict) -> dict[str, int | float]:
    """Convert analysis to side-to-move relative features (color-agnostic).

    All per-side features are expressed as stm (side to move) vs opp (opponent).
    eval_advantage is the engine eval from STM's perspective.

    Args:
        analysis: Output of board_utils.analyze_position(board).

    Returns:
        Dict mapping STM feature name → numeric value.
    """
    # First get absolute features
    abs_v = vectorize(analysis)
    is_white = analysis.get("side_to_move") == "white"

    # Engine eval from STM perspective
    eng = analysis.get("engine", {})
    eval_data = eng.get("eval") or {} if isinstance(eng, dict) else {}
    eval_cp = eval_data.get("score_cp", 0) or 0
    eval_advantage = eval_cp if is_white else -eval_cp

    # Map absolute features to STM-relative
    # Helper: pick stm/opp values based on side
    def stm_opp(white_key: str, black_key: str) -> tuple:
        if is_white:
            return abs_v[white_key], abs_v[black_key]
        return abs_v[black_key], abs_v[white_key]

    mat_w = analysis.get("material", {}).get("white", {})
    mat_b = analysis.get("material", {}).get("black", {})
    bp_stm = (mat_w if is_white else mat_b).get("bishop_pair", False)
    bp_opp = (mat_b if is_white else mat_w).get("bishop_pair", False)

    ks = analysis.get("king_safety", {})
    ks_stm = ks.get("white" if is_white else "black", {})
    ks_opp = ks.get("black" if is_white else "white", {})
    mate_by_stm = int(ks_opp.get("mate_threat") is not None)  # threat TO opponent's king
    mate_by_opp = int(ks_stm.get("mate_threat") is not None)  # threat TO stm's king

    # Material advantage from STM perspective
    mat_adv = abs_v["material_balance"] if is_white else -abs_v["material_balance"]

    stm_side = "white" if is_white else "black"
    opp_side = "black" if is_white else "white"

    q_stm, q_opp = stm_opp("queen_count_white", "queen_count_black")
    r_stm, r_opp = stm_opp("rook_count_white", "rook_count_black")
    m_stm, m_opp = stm_opp("minor_count_white", "minor_count_black")
    p_stm, p_opp = stm_opp("pawn_count_white", "pawn_count_black")

    pp_stm, pp_opp = stm_opp("passed_pawns_white", "passed_pawns_black")
    dp_stm, dp_opp = stm_opp("doubled_pawns_white", "doubled_pawns_black")
    ip_stm, ip_opp = stm_opp("isolated_pawns_white", "isolated_pawns_black")
    bp_stm_p, bp_opp_p = stm_opp("backward_pawns_white", "backward_pawns_black")
    pi_stm, pi_opp = stm_opp("pawn_islands_white", "pawn_islands_black")

    sa_stm, sa_opp = stm_opp("squares_attacked_white", "squares_attacked_black")
    cc_stm, cc_opp = stm_opp("center_control_white", "center_control_black")
    ko_stm, ko_opp = stm_opp("knight_outposts_white", "knight_outposts_black")
    rof_stm, rof_opp = stm_opp("rooks_on_open_files_white", "rooks_on_open_files_black")
    r7_stm, r7_opp = stm_opp("rooks_on_7th_white", "rooks_on_7th_black")

    sof_stm, sof_opp = stm_opp("semi_open_files_white", "semi_open_files_black")

    ps_stm, ps_opp = stm_opp("pawn_shield_white", "pawn_shield_black")
    ms_stm, ms_opp = stm_opp("missing_shield_white", "missing_shield_black")
    ka_stm, ka_opp = stm_opp("king_attackers_white", "king_attackers_black")
    cr_stm, cr_opp = stm_opp("castling_rights_white", "castling_rights_black")

    sp_stm, sp_opp = stm_opp("space_white", "space_black")
    dev_stm, dev_opp = stm_opp("development_white", "development_black")

    mps_stm, mps_opp = stm_opp("minor_piece_score_white", "minor_piece_score_black")
    bb_stm, bb_opp = stm_opp("bad_bishops_white", "bad_bishops_black")

    ini_stm, ini_opp = stm_opp("initiative_score_white", "initiative_score_black")
    chk_stm, chk_opp = stm_opp("checks_available_white", "checks_available_black")

    ss_stm, ss_opp = stm_opp("static_score_white", "static_score_black")
    ds_stm, ds_opp = stm_opp("dynamic_score_white", "dynamic_score_black")

    ft_stm, ft_opp = stm_opp("fork_threats_white", "fork_threats_black")
    sk_stm, sk_opp = stm_opp("skewer_threats_white", "skewer_threats_black")
    da_stm, da_opp = stm_opp("discovered_attack_threats_white", "discovered_attack_threats_black")
    cm_stm, cm_opp = stm_opp("checkmate_threats_white", "checkmate_threats_black")

    return {
        "material_advantage": mat_adv,
        "bishop_pair_stm": int(bp_stm),
        "bishop_pair_opp": int(bp_opp),
        "queen_count_stm": q_stm,
        "queen_count_opp": q_opp,
        "rook_count_stm": r_stm,
        "rook_count_opp": r_opp,
        "minor_count_stm": m_stm,
        "minor_count_opp": m_opp,
        "pawn_count_stm": p_stm,
        "pawn_count_opp": p_opp,

        "passed_pawns_stm": pp_stm,
        "passed_pawns_opp": pp_opp,
        "doubled_pawns_stm": dp_stm,
        "doubled_pawns_opp": dp_opp,
        "isolated_pawns_stm": ip_stm,
        "isolated_pawns_opp": ip_opp,
        "backward_pawns_stm": bp_stm_p,
        "backward_pawns_opp": bp_opp_p,
        "pawn_islands_stm": pi_stm,
        "pawn_islands_opp": pi_opp,

        "squares_attacked_stm": sa_stm,
        "squares_attacked_opp": sa_opp,
        "center_control_stm": cc_stm,
        "center_control_opp": cc_opp,
        "knight_outposts_stm": ko_stm,
        "knight_outposts_opp": ko_opp,
        "rooks_on_open_files_stm": rof_stm,
        "rooks_on_open_files_opp": rof_opp,
        "rooks_on_7th_stm": r7_stm,
        "rooks_on_7th_opp": r7_opp,

        "open_files": abs_v["open_files"],
        "semi_open_files_stm": sof_stm,
        "semi_open_files_opp": sof_opp,

        "pawn_shield_stm": ps_stm,
        "pawn_shield_opp": ps_opp,
        "missing_shield_stm": ms_stm,
        "missing_shield_opp": ms_opp,
        "king_attackers_stm": ka_stm,
        "king_attackers_opp": ka_opp,
        "castling_rights_stm": cr_stm,
        "castling_rights_opp": cr_opp,
        "mate_threat_by_stm": mate_by_stm,
        "mate_threat_by_opp": mate_by_opp,

        "space_stm": sp_stm,
        "space_opp": sp_opp,

        "development_stm": dev_stm,
        "development_opp": dev_opp,

        "minor_piece_score_stm": mps_stm,
        "minor_piece_score_opp": mps_opp,
        "bad_bishops_stm": bb_stm,
        "bad_bishops_opp": bb_opp,

        "initiative_score_stm": ini_stm,
        "initiative_score_opp": ini_opp,
        "checks_available_stm": chk_stm,
        "checks_available_opp": chk_opp,

        "static_score_stm": ss_stm,
        "static_score_opp": ss_opp,
        "dynamic_score_stm": ds_stm,
        "dynamic_score_opp": ds_opp,

        "pin_count": abs_v["pin_count"],
        "battery_count": abs_v["battery_count"],
        "hanging_pieces_count": abs_v["hanging_pieces_count"],
        "trapped_pieces_count": abs_v["trapped_pieces_count"],
        "fork_threats_stm": ft_stm,
        "fork_threats_opp": ft_opp,
        "skewer_threats_stm": sk_stm,
        "skewer_threats_opp": sk_opp,
        "discovered_attack_threats_stm": da_stm,
        "discovered_attack_threats_opp": da_opp,
        "checkmate_threats_stm": cm_stm,
        "checkmate_threats_opp": cm_opp,

        # ── Spatial context (STM-relative) ────────────────────────
        **_compute_spatial_features(analysis, is_white),

        "game_phase": abs_v["game_phase"],
        "total_non_pawn_material": abs_v["total_non_pawn_material"],
        "is_check": abs_v["is_check"],
        "eval_advantage": eval_advantage,
    }


def compute_deltas(
    v_before: dict[str, int | float],
    v_after: dict[str, int | float],
) -> dict[str, int | float]:
    """Compute element-wise deltas: v_after - v_before.

    Returns dict with keys prefixed by "d_" (e.g., "d_material_balance").
    """
    return {f"d_{k}": v_after[k] - v_before[k] for k in v_before}
