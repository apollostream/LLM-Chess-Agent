#!/usr/bin/env python3
"""Tactical motif detection for chess positions.

Detects 19 tactical patterns across three tiers:
- Tier 1 (Static): Board-scan patterns requiring no move calculation
- Tier 2 (Threats): Single-move tactical threats via legal move iteration
- Tier 3 (Sequences): 2-move forced sequences (forcing move → response → tactic)

Each detector returns a list of dicts describing found motifs.
The entry point is analyze_tactics(board) which returns the full nested structure.
"""

import chess

# ── Utilities ────────────────────────────────────────────────────────────────

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,  # King has no material value for tactics
}

PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


def _piece_value(piece_type: int) -> int:
    """Return the material value of a piece type."""
    return PIECE_VALUES.get(piece_type, 0)


def _piece_desc(board: chess.Board, sq: int) -> str:
    """Return 'piece on square' description, e.g. 'knight on f3'."""
    piece = board.piece_at(sq)
    if piece is None:
        return f"empty on {chess.square_name(sq)}"
    return f"{PIECE_NAMES[piece.piece_type]} on {chess.square_name(sq)}"


def _side_name(color: chess.Color) -> str:
    """Return 'white' or 'black'."""
    return "white" if color == chess.WHITE else "black"


def _ray_between(sq1: int, sq2: int) -> list[int]:
    """Return squares strictly between sq1 and sq2 on a rank/file/diagonal, or [] if not aligned."""
    r1, f1 = chess.square_rank(sq1), chess.square_file(sq1)
    r2, f2 = chess.square_rank(sq2), chess.square_file(sq2)

    dr = 0 if r2 == r1 else (1 if r2 > r1 else -1)
    df = 0 if f2 == f1 else (1 if f2 > f1 else -1)

    # Must be on same rank, file, or diagonal
    if dr == 0 and df == 0:
        return []
    if dr != 0 and df != 0 and abs(r2 - r1) != abs(f2 - f1):
        return []

    squares = []
    r, f = r1 + dr, f1 + df
    while (r, f) != (r2, f2):
        if not (0 <= r <= 7 and 0 <= f <= 7):
            return []
        squares.append(chess.square(f, r))
        r += dr
        f += df
    return squares


def _ray_beyond(sq_from: int, sq_through: int) -> list[int]:
    """Return squares continuing the ray from sq_from through sq_through, beyond sq_through."""
    r1, f1 = chess.square_rank(sq_from), chess.square_file(sq_from)
    r2, f2 = chess.square_rank(sq_through), chess.square_file(sq_through)

    dr = 0 if r2 == r1 else (1 if r2 > r1 else -1)
    df = 0 if f2 == f1 else (1 if f2 > f1 else -1)

    if dr == 0 and df == 0:
        return []
    if dr != 0 and df != 0 and abs(r2 - r1) != abs(f2 - f1):
        return []

    squares = []
    r, f = r2 + dr, f2 + df
    while 0 <= r <= 7 and 0 <= f <= 7:
        squares.append(chess.square(f, r))
        r += dr
        f += df
    return squares


def _slider_ray_directions(piece_type: int) -> list[tuple[int, int]]:
    """Return (dr, df) direction tuples for a sliding piece type."""
    if piece_type == chess.BISHOP:
        return [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    elif piece_type == chess.ROOK:
        return [(1, 0), (-1, 0), (0, 1), (0, -1)]
    elif piece_type == chess.QUEEN:
        return [(1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1)]
    return []


def _walk_ray(sq: int, dr: int, df: int) -> list[int]:
    """Walk a ray from sq in direction (dr, df), returning squares hit (not including sq)."""
    r, f = chess.square_rank(sq) + dr, chess.square_file(sq) + df
    squares = []
    while 0 <= r <= 7 and 0 <= f <= 7:
        squares.append(chess.square(f, r))
        r += dr
        f += df
    return squares


def _is_sliding_piece(piece_type: int) -> bool:
    return piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN)


def _can_slide_on_line(piece_type: int, dr: int, df: int) -> bool:
    """Check if a piece type can slide in the given direction."""
    if piece_type == chess.QUEEN:
        return True
    if piece_type == chess.ROOK:
        return dr == 0 or df == 0
    if piece_type == chess.BISHOP:
        return dr != 0 and df != 0
    return False


def _line_type(sq1: int, sq2: int) -> str | None:
    """Return 'rank', 'file', or 'diagonal' if squares are aligned, else None."""
    r1, f1 = chess.square_rank(sq1), chess.square_file(sq1)
    r2, f2 = chess.square_rank(sq2), chess.square_file(sq2)
    if r1 == r2:
        return "rank"
    if f1 == f2:
        return "file"
    if abs(r1 - r2) == abs(f1 - f2):
        return "diagonal"
    return None


# ── Tier 1: Static detectors ────────────────────────────────────────────────

def detect_pins(board: chess.Board) -> list[dict]:
    """Detect absolute and relative pins.

    Absolute: piece pinned to its own king (uses board.is_pinned).
    Relative: piece pinned to a more valuable piece behind it.
    """
    pins = []

    for color in [chess.WHITE, chess.BLACK]:
        enemy = not color
        king_sq = board.king(color)

        # Absolute pins (pinned to king)
        if king_sq is not None:
            for sq in chess.SQUARES:
                if board.is_pinned(color, sq):
                    piece = board.piece_at(sq)
                    if piece and piece.color == color and piece.piece_type != chess.KING:
                        pin_mask = board.pin(color, sq)
                        pinner_sq = None
                        for psq in chess.SQUARES:
                            ep = board.piece_at(psq)
                            if (ep and ep.color == enemy and
                                    psq in chess.SquareSet(pin_mask) and psq != sq):
                                pinner_sq = psq
                                break
                        pins.append({
                            "pinned_piece": _piece_desc(board, sq),
                            "pinned_to": _piece_desc(board, king_sq),
                            "pinner": _piece_desc(board, pinner_sq) if pinner_sq is not None else "unknown",
                            "pin_type": "absolute",
                            "pinned_side": _side_name(color),
                        })

        # Relative pins: enemy slider → piece A → more valuable piece B (same color)
        for slider_sq in chess.SQUARES:
            slider = board.piece_at(slider_sq)
            if not slider or slider.color != enemy or not _is_sliding_piece(slider.piece_type):
                continue

            for dr, df in _slider_ray_directions(slider.piece_type):
                ray = _walk_ray(slider_sq, dr, df)
                pieces_hit = []
                for rsq in ray:
                    p = board.piece_at(rsq)
                    if p is not None:
                        pieces_hit.append((rsq, p))
                        if len(pieces_hit) == 2:
                            break

                if len(pieces_hit) == 2:
                    sq_a, piece_a = pieces_hit[0]
                    sq_b, piece_b = pieces_hit[1]
                    # Both must be same color (the pinned side), and both friendly to 'color'
                    if (piece_a.color == color and piece_b.color == color and
                            piece_b.piece_type != chess.KING and  # absolute pin handled above
                            _piece_value(piece_a.piece_type) < _piece_value(piece_b.piece_type)):
                        # Check not already reported as absolute
                        if king_sq is not None and sq_b == king_sq:
                            continue
                        pins.append({
                            "pinned_piece": _piece_desc(board, sq_a),
                            "pinned_to": _piece_desc(board, sq_b),
                            "pinner": _piece_desc(board, slider_sq),
                            "pin_type": "relative",
                            "pinned_side": _side_name(color),
                        })

    return pins


def detect_batteries(board: chess.Board) -> list[dict]:
    """Detect batteries: two same-color sliding pieces aligned on the same line.

    A battery is two sliders on the same rank/file/diagonal where the front piece
    is supported by the rear piece sliding on the same line type.
    """
    batteries = []
    seen = set()

    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or not _is_sliding_piece(piece.piece_type):
            continue

        for dr, df in _slider_ray_directions(piece.piece_type):
            ray = _walk_ray(sq, dr, df)
            for rsq in ray:
                blocker = board.piece_at(rsq)
                if blocker is not None:
                    # Found first piece on this ray
                    if (blocker.color == piece.color and
                            _is_sliding_piece(blocker.piece_type) and
                            _can_slide_on_line(blocker.piece_type, dr, df)):
                        # Both can move on this line — it's a battery
                        key = (min(sq, rsq), max(sq, rsq))
                        if key not in seen:
                            seen.add(key)
                            lt = _line_type(sq, rsq)
                            batteries.append({
                                "pieces": [_piece_desc(board, sq), _piece_desc(board, rsq)],
                                "line": lt or "unknown",
                                "side": _side_name(piece.color),
                            })
                    break  # stop walking this ray after first piece

    return batteries


def detect_xray_attacks(board: chess.Board) -> list[dict]:
    """Detect x-ray attacks: slider attacks through an intervening piece to hit an enemy piece behind."""
    xrays = []

    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or not _is_sliding_piece(piece.piece_type):
            continue

        for dr, df in _slider_ray_directions(piece.piece_type):
            ray = _walk_ray(sq, dr, df)
            pieces_hit = []
            for rsq in ray:
                p = board.piece_at(rsq)
                if p is not None:
                    pieces_hit.append((rsq, p))
                    if len(pieces_hit) == 2:
                        break

            if len(pieces_hit) == 2:
                through_sq, through_piece = pieces_hit[0]
                target_sq, target_piece = pieces_hit[1]
                # X-ray: attacker sees through an intervening piece to an enemy piece
                # Filter out trivial x-rays (pawn through pawn)
                if (target_piece.color != piece.color and
                        _piece_value(target_piece.piece_type) >= 3):
                    xrays.append({
                        "attacker": _piece_desc(board, sq),
                        "through": _piece_desc(board, through_sq),
                        "target": _piece_desc(board, target_sq),
                        "side": _side_name(piece.color),
                    })

    return xrays


def detect_hanging_pieces(board: chess.Board) -> list[dict]:
    """Detect hanging pieces: undefended or underdefended pieces of the side NOT to move."""
    hanging = []
    stm = board.turn
    not_stm = not stm

    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or piece.color != not_stm:
            continue
        if piece.piece_type in (chess.PAWN, chess.KING):
            continue

        attacked = board.is_attacked_by(stm, sq)
        defended = board.is_attacked_by(not_stm, sq)

        if attacked and not defended:
            # Find lowest-value attacker
            attackers = board.attackers(stm, sq)
            lowest = min((_piece_value(board.piece_at(a).piece_type) for a in attackers),
                         default=99)
            hanging.append({
                "piece": _piece_desc(board, sq),
                "square": chess.square_name(sq),
                "side": _side_name(not_stm),
                "type": "undefended",
                "lowest_attacker_value": lowest,
            })
        elif attacked and defended:
            # Check if lowest attacker is worth less than the piece
            attackers = board.attackers(stm, sq)
            lowest_attacker_val = min(
                (_piece_value(board.piece_at(a).piece_type) for a in attackers), default=99)
            if lowest_attacker_val < _piece_value(piece.piece_type):
                hanging.append({
                    "piece": _piece_desc(board, sq),
                    "square": chess.square_name(sq),
                    "side": _side_name(not_stm),
                    "type": "underdefended",
                    "lowest_attacker_value": lowest_attacker_val,
                })

    return hanging


def detect_overloaded_pieces(board: chess.Board) -> list[dict]:
    """Detect overloaded defenders: a single piece that is the sole defender of 2+ attacked pieces."""
    overloaded = []
    stm = board.turn
    not_stm = not stm

    # Find all attacked pieces of the side not to move
    attacked_squares = []
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.color == not_stm and piece.piece_type != chess.KING:
            if board.is_attacked_by(stm, sq):
                attacked_squares.append(sq)

    # For each defender of the not-to-move side, count how many attacked pieces it solely defends
    defender_duties: dict[int, list[int]] = {}
    for atk_sq in attacked_squares:
        defenders = board.attackers(not_stm, atk_sq)
        # Exclude the piece itself from its own defenders
        defenders = chess.SquareSet(defenders) - chess.SquareSet([atk_sq])
        if len(defenders) == 1:
            sole_def = list(defenders)[0]
            if sole_def not in defender_duties:
                defender_duties[sole_def] = []
            defender_duties[sole_def].append(atk_sq)

    for def_sq, guarded_sqs in defender_duties.items():
        if len(guarded_sqs) >= 2:
            overloaded.append({
                "piece": _piece_desc(board, def_sq),
                "square": chess.square_name(def_sq),
                "side": _side_name(not_stm),
                "guarding": [_piece_desc(board, g) for g in guarded_sqs],
            })

    return overloaded


def detect_weak_back_rank(board: chess.Board) -> dict:
    """Detect weak back rank for both sides."""
    result = {}
    for color in [chess.WHITE, chess.BLACK]:
        king_sq = board.king(color)
        if king_sq is None:
            result[_side_name(color)] = {"is_weak": False}
            continue

        back_rank = 0 if color == chess.WHITE else 7
        king_rank = chess.square_rank(king_sq)

        if king_rank != back_rank:
            result[_side_name(color)] = {"is_weak": False}
            continue

        # Check if squares directly in front of king are blocked by own pawns
        front_rank = back_rank + (1 if color == chess.WHITE else -1)
        king_file = chess.square_file(king_sq)
        shield_files = [f for f in [king_file - 1, king_file, king_file + 1] if 0 <= f <= 7]

        blocked_count = 0
        for f in shield_files:
            front_sq = chess.square(f, front_rank)
            p = board.piece_at(front_sq)
            if p and p.color == color and p.piece_type == chess.PAWN:
                blocked_count += 1

        # Weak if all shield squares blocked by own pawns
        is_weak = blocked_count == len(shield_files)

        # Check if any friendly rook defends the back rank
        enemy = not color
        rook_defends = False
        for rook_sq in board.pieces(chess.ROOK, color):
            if chess.square_rank(rook_sq) == back_rank:
                rook_defends = True
                break
        # Queen on back rank also helps
        for q_sq in board.pieces(chess.QUEEN, color):
            if chess.square_rank(q_sq) == back_rank:
                rook_defends = True
                break

        if rook_defends:
            is_weak = False

        escape_squares = []
        for f in shield_files:
            front_sq = chess.square(f, front_rank)
            p = board.piece_at(front_sq)
            if not p or p.color != color or p.piece_type != chess.PAWN:
                escape_squares.append(chess.square_name(front_sq))

        result[_side_name(color)] = {
            "is_weak": is_weak,
            "escape_squares": escape_squares,
            "rook_defends_back_rank": rook_defends,
        }

    return result


def detect_trapped_pieces(board: chess.Board) -> list[dict]:
    """Detect trapped pieces: minor/major pieces with no safe squares."""
    trapped = []
    stm = board.turn

    for color in [chess.WHITE, chess.BLACK]:
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if not piece or piece.color != color:
                continue
            if piece.piece_type in (chess.PAWN, chess.KING):
                continue
            if _piece_value(piece.piece_type) < 3:
                continue

            # Check all squares this piece attacks — are any safe?
            safe_squares = []
            for target_sq in board.attacks(sq):
                # A square is "safe" if not attacked by enemy piece of <= value,
                # or if it captures a piece (escape by capture)
                target_piece = board.piece_at(target_sq)
                if target_piece and target_piece.color == color:
                    continue  # can't go to own-piece square

                enemy = not color
                enemy_attackers = board.attackers(enemy, target_sq)
                if not enemy_attackers:
                    safe_squares.append(target_sq)
                elif target_piece and target_piece.color == enemy:
                    # Capture: safe only if we win material (capture value > our piece)
                    # or if square is undefended after capture (no recapture)
                    capture_val = _piece_value(target_piece.piece_type)
                    our_val = _piece_value(piece.piece_type)
                    # Exclude the captured piece from defenders of the square
                    remaining_defenders = chess.SquareSet(enemy_attackers) - chess.SquareSet([target_sq])
                    if capture_val > our_val:
                        safe_squares.append(target_sq)
                    elif not remaining_defenders:
                        safe_squares.append(target_sq)

            is_attacked = board.is_attacked_by(not color, sq)
            if len(safe_squares) == 0 and (is_attacked or len(list(board.attacks(sq))) == 0):
                trapped.append({
                    "piece": _piece_desc(board, sq),
                    "square": chess.square_name(sq),
                    "side": _side_name(color),
                    "safe_squares": len(safe_squares),
                })

    return trapped


def detect_advanced_passed_pawns(board: chess.Board) -> list[dict]:
    """Detect passed pawns on rank 6+ (White) or rank 3- (Black)."""
    advanced = []

    for color in [chess.WHITE, chess.BLACK]:
        enemy = not color
        pawns = board.pieces(chess.PAWN, color)
        enemy_pawns = board.pieces(chess.PAWN, enemy)

        for sq in pawns:
            f = chess.square_file(sq)
            r = chess.square_rank(sq)

            # Check rank threshold: rank 6+ for White (index 5+), rank 3- for Black (index 2-)
            if color == chess.WHITE and r < 5:
                continue
            if color == chess.BLACK and r > 2:
                continue

            # Check if passed
            blocking_files = [bf for bf in [f - 1, f, f + 1] if 0 <= bf <= 7]
            is_passed = True
            for ep in enemy_pawns:
                ef = chess.square_file(ep)
                er = chess.square_rank(ep)
                if ef in blocking_files:
                    if color == chess.WHITE and er > r:
                        is_passed = False
                        break
                    elif color == chess.BLACK and er < r:
                        is_passed = False
                        break

            if not is_passed:
                continue

            # Check if protected by own pawn
            is_protected = False
            for p in pawns:
                if p != sq and sq in board.attacks(p):
                    is_protected = True
                    break

            advanced.append({
                "square": chess.square_name(sq),
                "side": _side_name(color),
                "rank": r + 1,  # human-readable rank
                "is_protected": is_protected,
            })

    return advanced


def detect_alignments(board: chess.Board) -> list[dict]:
    """Detect alignments of high-value pieces (K, Q, R) on ranks/files/diagonals
    that could be exploited by enemy sliders."""
    alignments = []
    high_value_types = {chess.KING, chess.QUEEN, chess.ROOK}

    for color in [chess.WHITE, chess.BLACK]:
        enemy = not color
        # Collect high-value piece squares for this color
        hv_squares = []
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.color == color and piece.piece_type in high_value_types:
                hv_squares.append(sq)

        # Check all pairs
        for i in range(len(hv_squares)):
            for j in range(i + 1, len(hv_squares)):
                sq1, sq2 = hv_squares[i], hv_squares[j]
                lt = _line_type(sq1, sq2)
                if lt is None:
                    continue

                # Determine direction
                r1, f1 = chess.square_rank(sq1), chess.square_file(sq1)
                r2, f2 = chess.square_rank(sq2), chess.square_file(sq2)
                dr = 0 if r2 == r1 else (1 if r2 > r1 else -1)
                df = 0 if f2 == f1 else (1 if f2 > f1 else -1)

                # Check if an enemy slider could exploit this alignment
                # Look for enemy sliders that can move on this line type
                potential = None
                for esq in chess.SQUARES:
                    ep = board.piece_at(esq)
                    if not ep or ep.color != enemy or not _is_sliding_piece(ep.piece_type):
                        continue
                    if not _can_slide_on_line(ep.piece_type, dr, df):
                        continue
                    # Check if this slider is on the same line
                    lt_to_sq1 = _line_type(esq, sq1)
                    lt_to_sq2 = _line_type(esq, sq2)
                    if lt_to_sq1 == lt and lt_to_sq2 == lt:
                        # Determine if it could be a pin or skewer
                        p1_val = _piece_value(board.piece_at(sq1).piece_type)
                        p2_val = _piece_value(board.piece_at(sq2).piece_type)
                        if p1_val >= p2_val:
                            potential = "skewer"
                        else:
                            potential = "pin"
                        break

                if potential:
                    alignments.append({
                        "pieces": [_piece_desc(board, sq1), _piece_desc(board, sq2)],
                        "line": lt,
                        "side": _side_name(color),
                        "potential": potential,
                    })

    return alignments


# ── Tier 2: Threat detectors (single move) ──────────────────────────────────

def detect_forks(board: chess.Board) -> list[dict]:
    """Detect fork threats: moves that attack 2+ enemy pieces worth >= pawn."""
    forks = []
    stm = board.turn

    for move in board.legal_moves:
        board.push(move)
        to_sq = move.to_square
        moving_piece = board.piece_at(to_sq)
        if moving_piece is None:
            board.pop()
            continue

        attacks = board.attacks(to_sq)
        targets = []
        for atk_sq in attacks:
            target = board.piece_at(atk_sq)
            if target and target.color != stm and (
                    _piece_value(target.piece_type) >= 1 or target.piece_type == chess.KING):
                # King is always a valuable fork target (effectively infinite)
                effective_value = 100 if target.piece_type == chess.KING else _piece_value(target.piece_type)
                targets.append({
                    "piece": _piece_desc(board, atk_sq),
                    "value": effective_value,
                })

        if len(targets) >= 2:
            total_target_value = sum(t["value"] for t in targets)
            moving_value = _piece_value(moving_piece.piece_type)
            # Only report if targets are worth capturing or includes king
            if total_target_value > moving_value or any(t["value"] >= 3 for t in targets):
                forks.append({
                    "move": board.peek().uci() if board.move_stack else move.uci(),
                    "move_san": None,  # filled below
                    "forking_piece": PIECE_NAMES[moving_piece.piece_type],
                    "targets": [t["piece"] for t in targets],
                    "side": _side_name(stm),
                })
        board.pop()

    # Fill in SAN notation
    for fork in forks:
        try:
            m = chess.Move.from_uci(fork["move"])
            fork["move_san"] = board.san(m)
        except (ValueError, AssertionError):
            fork["move_san"] = fork["move"]
        del fork["move"]
        fork["move"] = fork.pop("move_san")

    return forks


def detect_skewers(board: chess.Board) -> list[dict]:
    """Detect skewer threats: sliding piece attacks valuable piece with less valuable piece behind."""
    skewers = []
    stm = board.turn

    for move in board.legal_moves:
        to_sq = move.to_square
        piece = board.piece_at(move.from_square)
        if not piece or not _is_sliding_piece(piece.piece_type):
            continue

        board.push(move)
        moved_piece = board.piece_at(to_sq)
        if moved_piece is None:
            board.pop()
            continue

        for dr, df in _slider_ray_directions(moved_piece.piece_type):
            ray = _walk_ray(to_sq, dr, df)
            pieces_hit = []
            for rsq in ray:
                p = board.piece_at(rsq)
                if p is not None:
                    pieces_hit.append((rsq, p))
                    if len(pieces_hit) == 2:
                        break

            if len(pieces_hit) == 2:
                sq_a, piece_a = pieces_hit[0]
                sq_b, piece_b = pieces_hit[1]
                if (piece_a.color != stm and piece_b.color != stm and
                        _piece_value(piece_a.piece_type) > _piece_value(piece_b.piece_type) and
                        _piece_value(piece_a.piece_type) >= 3):
                    # It's a skewer: attacks valuable front target, less valuable behind
                    san = board.peek().uci()
                    board.pop()
                    try:
                        san = board.san(move)
                    except (ValueError, AssertionError):
                        san = move.uci()
                    skewers.append({
                        "move": san,
                        "skewering_piece": PIECE_NAMES[moved_piece.piece_type],
                        "front_target": _piece_desc(board, sq_a),
                        "rear_target": _piece_desc(board, sq_b),
                        "side": _side_name(stm),
                    })
                    break  # only report one skewer per move
            # continue to next direction
        else:
            board.pop()
            continue
        # If we broke out of the directions loop (found skewer), we already popped
        continue

    return skewers


def detect_discovered_attacks(board: chess.Board) -> list[dict]:
    """Detect discovered attacks: moving a piece reveals a slider attacking an enemy piece."""
    discovered = []
    stm = board.turn

    # Pre-compute: find pieces sitting on rays between friendly sliders and enemy targets
    blocker_info = []  # (blocker_sq, slider_sq, target_sq)
    for slider_sq in chess.SQUARES:
        slider = board.piece_at(slider_sq)
        if not slider or slider.color != stm or not _is_sliding_piece(slider.piece_type):
            continue

        for dr, df in _slider_ray_directions(slider.piece_type):
            ray = _walk_ray(slider_sq, dr, df)
            first_piece_sq = None
            for rsq in ray:
                p = board.piece_at(rsq)
                if p is not None:
                    if first_piece_sq is None:
                        # This is the potential blocker
                        if p.color == stm and p.piece_type != chess.KING:
                            first_piece_sq = rsq
                        else:
                            break  # enemy piece or king blocks
                    else:
                        # This is the potential target
                        if p.color != stm and _piece_value(p.piece_type) >= 1:
                            blocker_info.append((first_piece_sq, slider_sq, rsq))
                        break

    # For each blocker's legal moves, check if slider now attacks the target
    seen_moves = set()
    for blocker_sq, slider_sq, target_sq in blocker_info:
        for move in board.legal_moves:
            if move.from_square != blocker_sq:
                continue
            if move in seen_moves:
                continue

            board.push(move)
            # Verify slider now attacks target
            slider_attacks = board.attacks(slider_sq)
            if target_sq in slider_attacks:
                san = board.peek().uci()
                board.pop()
                try:
                    san = board.san(move)
                except (ValueError, AssertionError):
                    san = move.uci()
                seen_moves.add(move)
                discovered.append({
                    "move": san,
                    "moving_piece": _piece_desc(board, blocker_sq),
                    "revealed_attacker": _piece_desc(board, slider_sq),
                    "target": _piece_desc(board, target_sq),
                    "side": _side_name(stm),
                })
            else:
                board.pop()

    return discovered


def detect_discovered_checks(board: chess.Board) -> list[dict]:
    """Detect discovered checks: moving a piece reveals check from a friendly slider."""
    disc_checks = []
    stm = board.turn

    for move in board.legal_moves:
        board.push(move)
        if board.is_check():
            # Check if the moved piece itself gives check
            to_sq = move.to_square
            enemy_king = board.king(not stm)
            if enemy_king is not None:
                moved_piece = board.piece_at(to_sq)
                moved_gives_check = enemy_king in board.attacks(to_sq) if moved_piece else False

                if not moved_gives_check:
                    # It's a discovered check — find the checking piece
                    checkers = board.attackers(stm, enemy_king)
                    checking_pieces = [sq for sq in checkers if sq != to_sq]
                    if checking_pieces:
                        board.pop()
                        try:
                            san = board.san(move)
                        except (ValueError, AssertionError):
                            san = move.uci()
                        disc_checks.append({
                            "move": san,
                            "moving_piece": _piece_desc(board, move.from_square),
                            "checking_piece": _piece_desc(board, checking_pieces[0]),
                            "side": _side_name(stm),
                        })
                        continue
        board.pop()

    return disc_checks


def detect_double_checks(board: chess.Board) -> list[dict]:
    """Detect double checks: moves that give check from 2+ pieces simultaneously."""
    double_checks = []
    stm = board.turn

    for move in board.legal_moves:
        board.push(move)
        if board.is_check():
            enemy_king = board.king(not stm)
            if enemy_king is not None:
                checkers = board.attackers(stm, enemy_king)
                if len(checkers) >= 2:
                    board.pop()
                    try:
                        san = board.san(move)
                    except (ValueError, AssertionError):
                        san = move.uci()
                    double_checks.append({
                        "move": san,
                        "checkers": [_piece_desc(board, sq) for sq in checkers],
                        "side": _side_name(stm),
                    })
                    continue
        board.pop()

    return double_checks


def detect_back_rank_mates(board: chess.Board) -> list[dict]:
    """Detect back rank mate threats: moves that deliver checkmate with king on back rank."""
    mates = []
    stm = board.turn

    for move in board.legal_moves:
        board.push(move)
        if board.is_checkmate():
            enemy_king = board.king(not stm)
            if enemy_king is not None:
                back_rank = 0 if (not stm) == chess.WHITE else 7
                if chess.square_rank(enemy_king) == back_rank:
                    board.pop()
                    try:
                        san = board.san(move)
                    except (ValueError, AssertionError):
                        san = move.uci()
                    mates.append({
                        "move": san,
                        "side": _side_name(stm),
                    })
                    continue
        board.pop()

    return mates


def detect_removal_of_guard(board: chess.Board) -> list[dict]:
    """Detect removal of guard: capturing a piece that was defending something important."""
    removals = []
    stm = board.turn

    for move in board.legal_moves:
        if not board.is_capture(move):
            continue

        captured_sq = move.to_square
        captured_piece = board.piece_at(captured_sq)
        if not captured_piece:
            # En passant
            continue

        # What was the captured piece defending?
        defended_by_captured = []
        for sq in chess.SQUARES:
            target = board.piece_at(sq)
            if target and target.color != stm and sq != captured_sq and target.piece_type != chess.KING:
                if captured_sq in board.attackers(not stm, sq):
                    defended_by_captured.append(sq)

        if not defended_by_captured:
            continue

        # Push the capture and check if any of those defended pieces are now hanging
        board.push(move)
        newly_hanging = []
        for sq in defended_by_captured:
            target = board.piece_at(sq)
            if target and target.color != stm:
                attacked = board.is_attacked_by(stm, sq)
                defended = board.is_attacked_by(not stm, sq)
                if attacked and not defended:
                    newly_hanging.append(sq)
        board.pop()

        if newly_hanging:
            try:
                san = board.san(move)
            except (ValueError, AssertionError):
                san = move.uci()
            for h_sq in newly_hanging:
                removals.append({
                    "move": san,
                    "captured_guard": _piece_desc(board, captured_sq),
                    "exposed_piece": _piece_desc(board, h_sq),
                    "side": _side_name(stm),
                })

    return removals


# ── Tier 3: Sequence detectors (2-move) ─────────────────────────────────────

def detect_deflections(board: chess.Board) -> list[dict]:
    """Detect deflections: a forcing move (check/capture) that deflects a defender,
    enabling a tactic on the next move."""
    deflections = []
    stm = board.turn

    for move in board.legal_moves:
        # Only consider forcing moves: checks and captures
        is_capture = board.is_capture(move)
        board.push(move)
        is_check = board.is_check()

        if not is_capture and not is_check:
            board.pop()
            continue

        if board.is_checkmate() or board.is_stalemate():
            board.pop()
            continue

        # For each opponent response
        found = False
        for response in board.legal_moves:
            board.push(response)

            # Check if side-to-move (original stm) now has a winning tactic
            # Look for: mate, hanging piece capture worth >= 3
            for followup in board.legal_moves:
                board.push(followup)
                is_mate = board.is_checkmate()
                board.pop()

                if is_mate:
                    board.pop()  # response
                    board.pop()  # forcing move
                    try:
                        forcing_san = board.san(move)
                    except (ValueError, AssertionError):
                        forcing_san = move.uci()
                    board.push(move)
                    try:
                        followup_san = board.san(followup) if followup in board.legal_moves else followup.uci()
                    except (ValueError, AssertionError):
                        followup_san = followup.uci()
                    board.pop()

                    deflections.append({
                        "forcing_move": forcing_san,
                        "target_piece": _piece_desc(board, move.to_square),
                        "followup": f"mate after {followup.uci()}",
                        "side": _side_name(stm),
                    })
                    found = True
                    break

                # Check for hanging piece capture
                if board.is_capture(followup):
                    cap_sq = followup.to_square
                    # Look at position before followup
                    cap_piece = board.piece_at(cap_sq)
                    if cap_piece and _piece_value(cap_piece.piece_type) >= 3:
                        # Was this piece defended before the forcing move?
                        pass  # Complex check — skip for now to avoid false positives

            if found:
                break
            board.pop()  # response

        if not found:
            board.pop()  # forcing move

    return deflections


def detect_zwischenzug(board: chess.Board) -> list[dict]:
    """Detect zwischenzug: after a capture, opponent has an intermediate check before recapturing."""
    zwischenzugs = []
    stm = board.turn

    for move in board.legal_moves:
        if not board.is_capture(move):
            continue

        cap_sq = move.to_square
        board.push(move)

        # Check if opponent has an intermediate check (instead of recapturing)
        recapture_exists = False
        intermediate_checks = []

        for response in board.legal_moves:
            # Is this a recapture?
            if response.to_square == cap_sq:
                recapture_exists = True

            # Is this an intermediate check?
            board.push(response)
            if board.is_check() and response.to_square != cap_sq:
                intermediate_checks.append(response)
            board.pop()

        board.pop()

        if recapture_exists and intermediate_checks:
            try:
                cap_san = board.san(move)
            except (ValueError, AssertionError):
                cap_san = move.uci()

            for zz in intermediate_checks:
                board.push(move)
                try:
                    zz_san = board.san(zz)
                except (ValueError, AssertionError):
                    zz_san = zz.uci()
                board.pop()

                zwischenzugs.append({
                    "expected_recapture": f"recapture on {chess.square_name(cap_sq)}",
                    "zwischenzug_move": zz_san,
                    "capture": cap_san,
                    "side": _side_name(not stm),  # The opponent plays the zwischenzug
                })

    return zwischenzugs


def detect_smothered_mates(board: chess.Board) -> list[dict]:
    """Detect smothered mates: knight delivers checkmate with enemy king surrounded by own pieces."""
    smothered = []
    stm = board.turn

    # 1-ply: direct smothered mate
    for move in board.legal_moves:
        piece = board.piece_at(move.from_square)
        if not piece or piece.piece_type != chess.KNIGHT:
            continue

        board.push(move)
        if board.is_checkmate():
            enemy_king = board.king(not stm)
            if enemy_king is not None:
                # Check if king is surrounded by own pieces
                king_rank = chess.square_rank(enemy_king)
                king_file = chess.square_file(enemy_king)
                surrounded = True
                for dr in [-1, 0, 1]:
                    for df in [-1, 0, 1]:
                        if dr == 0 and df == 0:
                            continue
                        r, f = king_rank + dr, king_file + df
                        if 0 <= r <= 7 and 0 <= f <= 7:
                            adj_sq = chess.square(f, r)
                            adj_piece = board.piece_at(adj_sq)
                            if adj_piece is None or adj_piece.color == stm:
                                # Empty or enemy piece — not surrounded
                                if adj_sq != move.to_square:  # knight is there
                                    surrounded = False
                                    break
                    if not surrounded:
                        break

                if surrounded:
                    board.pop()
                    try:
                        san = board.san(move)
                    except (ValueError, AssertionError):
                        san = move.uci()
                    smothered.append({
                        "move": san,
                        "side": _side_name(stm),
                    })
                    continue
        board.pop()

    # 2-ply: queen sacrifice → forced recapture → knight mate
    # Check if any queen sacrifice with check forces a recapture that allows smothered mate
    for move in board.legal_moves:
        piece = board.piece_at(move.from_square)
        if not piece or piece.piece_type != chess.QUEEN:
            continue

        board.push(move)
        if not board.is_check():
            board.pop()
            continue

        # Check if opponent's only response is to capture the queen
        responses = list(board.legal_moves)
        queen_captures = [r for r in responses if r.to_square == move.to_square]
        if len(responses) != len(queen_captures) or len(responses) == 0:
            board.pop()
            continue

        # For each forced recapture, check if we have a smothered mate
        for response in queen_captures:
            board.push(response)
            for followup in board.legal_moves:
                fp = board.piece_at(followup.from_square)
                if not fp or fp.piece_type != chess.KNIGHT:
                    continue
                board.push(followup)
                if board.is_checkmate():
                    enemy_king = board.king(not stm)
                    if enemy_king is not None:
                        king_rank = chess.square_rank(enemy_king)
                        king_file = chess.square_file(enemy_king)
                        is_smothered = True
                        for dr in [-1, 0, 1]:
                            for df in [-1, 0, 1]:
                                if dr == 0 and df == 0:
                                    continue
                                r, f = king_rank + dr, king_file + df
                                if 0 <= r <= 7 and 0 <= f <= 7:
                                    adj_sq = chess.square(f, r)
                                    adj_piece = board.piece_at(adj_sq)
                                    if adj_piece is None or adj_piece.color == stm:
                                        if adj_sq != followup.to_square:
                                            is_smothered = False
                                            break
                            if not is_smothered:
                                break

                        if is_smothered:
                            board.pop()  # followup
                            board.pop()  # response
                            board.pop()  # move
                            try:
                                sac_san = board.san(move)
                            except (ValueError, AssertionError):
                                sac_san = move.uci()
                            smothered.append({
                                "sequence": [sac_san, "recapture", "knight mate"],
                                "side": _side_name(stm),
                            })
                            # Avoid further iteration after triple pop
                            goto_next_move = True
                            break
                board.pop()  # followup
            else:
                board.pop()  # response
                continue
            # Broke out of followup loop — check if we did triple pop
            if 'goto_next_move' in dir():
                del goto_next_move
                break
            board.pop()  # response
        else:
            board.pop()  # move
            continue
        # Broke out of response loop after triple pop
        continue

    return smothered


# ── Entry point ──────────────────────────────────────────────────────────────

def analyze_tactics(board: chess.Board) -> dict:
    """Run all tactical motif detectors and return the full nested structure."""
    return {
        "static": {
            "pins": detect_pins(board),
            "batteries": detect_batteries(board),
            "xray_attacks": detect_xray_attacks(board),
            "hanging_pieces": detect_hanging_pieces(board),
            "overloaded_pieces": detect_overloaded_pieces(board),
            "weak_back_rank": detect_weak_back_rank(board),
            "trapped_pieces": detect_trapped_pieces(board),
            "advanced_passed_pawns": detect_advanced_passed_pawns(board),
            "alignments": detect_alignments(board),
        },
        "threats": {
            "forks": detect_forks(board),
            "skewers": detect_skewers(board),
            "discovered_attacks": detect_discovered_attacks(board),
            "discovered_checks": detect_discovered_checks(board),
            "double_checks": detect_double_checks(board),
            "back_rank_mates": detect_back_rank_mates(board),
            "removal_of_guard": detect_removal_of_guard(board),
        },
        "sequences": {
            "deflections": detect_deflections(board),
            "zwischenzug": detect_zwischenzug(board),
            "smothered_mates": detect_smothered_mates(board),
        },
    }
