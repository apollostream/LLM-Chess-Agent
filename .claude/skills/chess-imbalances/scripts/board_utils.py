#!/usr/bin/env python3
"""Chess position analysis engine using python-chess.

Produces structured JSON reports covering material, pawn structure,
piece activity, king safety, space, and more — the raw data that
feeds Silman's imbalance framework.

Usage:
    python board_utils.py <FEN | PGN_FILE | MOVES>
    python board_utils.py --format text <FEN | PGN_FILE | MOVES>
    python board_utils.py --move 15 game.pgn          # after White's 15th
    python board_utils.py --move 15b game.pgn         # after Black's 15th
"""

import argparse
import json
import os
import sys
from pathlib import Path

import chess
import chess.pgn

from tactical_motifs import analyze_tactics
from engine_eval import EngineEval


# ── Piece values ──────────────────────────────────────────────────────────────

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}

PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}

STARTING_SQUARES = {
    chess.WHITE: {
        chess.PAWN:   [chess.A2, chess.B2, chess.C2, chess.D2,
                       chess.E2, chess.F2, chess.G2, chess.H2],
        chess.KNIGHT: [chess.B1, chess.G1],
        chess.BISHOP: [chess.C1, chess.F1],
        chess.ROOK:   [chess.A1, chess.H1],
        chess.QUEEN:  [chess.D1],
        chess.KING:   [chess.E1],
    },
    chess.BLACK: {
        chess.PAWN:   [chess.A7, chess.B7, chess.C7, chess.D7,
                       chess.E7, chess.F7, chess.G7, chess.H7],
        chess.KNIGHT: [chess.B8, chess.G8],
        chess.BISHOP: [chess.C8, chess.F8],
        chess.ROOK:   [chess.A8, chess.H8],
        chess.QUEEN:  [chess.D8],
        chess.KING:   [chess.E8],
    },
}

CENTER_SQUARES = [chess.D4, chess.D5, chess.E4, chess.E5]
EXTENDED_CENTER = CENTER_SQUARES + [
    chess.C3, chess.C4, chess.C5, chess.C6,
    chess.D3, chess.D6,
    chess.E3, chess.E6,
    chess.F3, chess.F4, chess.F5, chess.F6,
]


# ── Input parsing ─────────────────────────────────────────────────────────────

def parse_move_target(move_str: str) -> tuple[int, bool]:
    """Parse a --move value like '15' (after White's 15th) or '15b' (after Black's 15th).

    Returns (fullmove_number, after_black).
    """
    move_str = move_str.strip().lower()
    if move_str.endswith("b"):
        return int(move_str[:-1]), True
    elif move_str.endswith("w"):
        return int(move_str[:-1]), False
    else:
        # Plain number means after White's move
        return int(move_str), False


def advance_to_move(node, move_target: str) -> chess.Board:
    """Walk a game tree to the position after the specified move number.

    move_target: e.g. '15' (after White's 15th), '15b' (after Black's 15th).
    """
    target_move, after_black = parse_move_target(move_target)

    current = node
    while current.variations:
        current = current.variations[0]
        board = current.board()
        move_num = board.fullmove_number
        # After White's move: it's now Black's turn, fullmove_number == target
        if not after_black and board.turn == chess.BLACK and move_num == target_move:
            return board
        # After Black's move: it's now White's turn, fullmove_number == target + 1
        if after_black and board.turn == chess.WHITE and move_num == target_move + 1:
            return board

    raise ValueError(
        f"Move {move_target} not found in game "
        f"(game ends at move {current.board().fullmove_number})"
    )


def detect_input(raw: str, move: str | None = None) -> tuple[str, chess.Board]:
    """Auto-detect input type and return (input_type, board).

    If move is specified, navigate to that move number (PGN and move-list only).
    """
    raw = raw.strip()

    # PGN file path
    if os.path.isfile(raw) and raw.endswith(".pgn"):
        return parse_pgn_file(raw, move)

    # FEN string (has at least 6 space-separated parts, or contains '/')
    if "/" in raw:
        if move:
            print("Warning: --move is ignored for FEN input", file=sys.stderr)
        try:
            board = chess.Board(raw)
            return "fen", board
        except ValueError:
            pass

    # Move list (e.g. "1. e4 e5 2. Nf3 Nc6")
    try:
        board = chess.Board()
        # Strip move numbers
        tokens = raw.replace(".", " ").split()
        for token in tokens:
            token = token.strip()
            if not token or token[0].isdigit():
                continue
            board.push_san(token)

        if move:
            # Replay from scratch with move target
            game = chess.pgn.Game()
            replay_board = chess.Board()
            node = game
            tokens = raw.replace(".", " ").split()
            for token in tokens:
                token = token.strip()
                if not token or token[0].isdigit():
                    continue
                m = replay_board.parse_san(token)
                node = node.add_variation(m)
                replay_board.push(m)
            board = advance_to_move(game, move)

        return "moves", board
    except (ValueError, chess.IllegalMoveError, chess.InvalidMoveError,
            chess.AmbiguousMoveError):
        pass

    raise ValueError(f"Cannot parse input as FEN, PGN file, or move list: {raw!r}")


def parse_pgn_file(path: str, move: str | None = None) -> tuple[str, chess.Board]:
    """Parse a PGN file and return the position at the specified move (or final)."""
    with open(path) as f:
        game = chess.pgn.read_game(f)
    if game is None:
        raise ValueError(f"No game found in PGN file: {path}")

    if move:
        board = advance_to_move(game, move)
    else:
        board = game.end().board()
    return "pgn", board


# ── Analysis functions ────────────────────────────────────────────────────────

def analyze_material(board: chess.Board) -> dict:
    """Count pieces and calculate material balance."""
    result = {}
    for color_name, color in [("white", chess.WHITE), ("black", chess.BLACK)]:
        counts = {}
        total = 0
        for pt in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            n = len(board.pieces(pt, color))
            counts[PIECE_NAMES[pt] + "s"] = n
            total += n * PIECE_VALUES[pt]
        counts["total_points"] = total
        result[color_name] = counts

    result["balance"] = result["white"]["total_points"] - result["black"]["total_points"]
    result["balance_description"] = (
        "equal" if result["balance"] == 0
        else f"White +{result['balance']}" if result["balance"] > 0
        else f"Black +{-result['balance']}"
    )

    # Bishop pair detection
    for color_name, color in [("white", chess.WHITE), ("black", chess.BLACK)]:
        bishops = board.pieces(chess.BISHOP, color)
        has_pair = False
        if len(bishops) >= 2:
            colors_of_bishops = {chess.square_rank(sq) % 2 == chess.square_file(sq) % 2
                                 for sq in bishops}
            has_pair = len(colors_of_bishops) == 2
        result[color_name]["bishop_pair"] = has_pair

    return result


def analyze_pawn_structure(board: chess.Board) -> dict:
    """Analyze pawn structure for both sides."""
    result = {}
    for color_name, color in [("white", chess.WHITE), ("black", chess.BLACK)]:
        enemy = not color
        pawns = board.pieces(chess.PAWN, color)
        enemy_pawns = board.pieces(chess.PAWN, enemy)

        pawn_files = [chess.square_file(sq) for sq in pawns]
        enemy_pawn_files = [chess.square_file(sq) for sq in enemy_pawns]

        # Doubled pawns
        doubled = []
        for f in range(8):
            pawns_on_file = [sq for sq in pawns if chess.square_file(sq) == f]
            if len(pawns_on_file) > 1:
                doubled.extend(chess.square_name(sq) for sq in pawns_on_file)

        # Isolated pawns
        isolated = []
        for sq in pawns:
            f = chess.square_file(sq)
            adj_files = [af for af in [f - 1, f + 1] if 0 <= af <= 7]
            if not any(chess.square_file(p) in adj_files for p in pawns):
                isolated.append(chess.square_name(sq))

        # Passed pawns
        passed = []
        for sq in pawns:
            f = chess.square_file(sq)
            r = chess.square_rank(sq)
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
            if is_passed:
                passed.append(chess.square_name(sq))

        # Backward pawns
        backward = []
        for sq in pawns:
            f = chess.square_file(sq)
            r = chess.square_rank(sq)
            adj_files = [af for af in [f - 1, f + 1] if 0 <= af <= 7]

            # Check if any friendly pawn on adjacent files at same rank or behind
            has_support = False
            for p in pawns:
                if p == sq:
                    continue
                pf = chess.square_file(p)
                pr = chess.square_rank(p)
                if pf in adj_files:
                    if color == chess.WHITE and pr <= r:
                        has_support = True
                        break
                    elif color == chess.BLACK and pr >= r:
                        has_support = True
                        break
            if has_support:
                continue

            # Check if advance square is attacked by enemy pawn
            advance_sq = sq + (8 if color == chess.WHITE else -8)
            if 0 <= advance_sq <= 63:
                advance_attacked_by_enemy_pawn = False
                for ep in enemy_pawns:
                    if advance_sq in board.attacks(ep):
                        advance_attacked_by_enemy_pawn = True
                        break
                if advance_attacked_by_enemy_pawn:
                    backward.append(chess.square_name(sq))

        # Pawn islands
        files_with_pawns = sorted(set(pawn_files))
        islands = 0
        if files_with_pawns:
            islands = 1
            for i in range(1, len(files_with_pawns)):
                if files_with_pawns[i] - files_with_pawns[i - 1] > 1:
                    islands += 1

        # Chain bases (pawns that are not defended by other pawns)
        chain_bases = []
        for sq in pawns:
            defended_by_pawn = False
            for p in pawns:
                if p == sq:
                    continue
                if sq in board.attacks(p):
                    defended_by_pawn = True
                    break
            if not defended_by_pawn and chess.square_name(sq) not in isolated:
                chain_bases.append(chess.square_name(sq))

        result[color_name] = {
            "pawn_count": len(pawns),
            "doubled": doubled,
            "isolated": isolated,
            "backward": backward,
            "passed": passed,
            "pawn_islands": islands,
            "chain_bases": chain_bases,
        }

    return result


def analyze_piece_activity(board: chess.Board) -> dict:
    """Analyze piece activity and placement for both sides."""
    result = {}
    for color_name, color in [("white", chess.WHITE), ("black", chess.BLACK)]:
        enemy = not color
        enemy_pawns = board.pieces(chess.PAWN, enemy)

        # Squares attacked
        attacked = set()
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.color == color:
                attacked.update(board.attacks(sq))
        total_attacked = len(attacked)

        # Center control
        center_control = [chess.square_name(sq) for sq in CENTER_SQUARES if sq in attacked]

        # Knight outposts
        outposts = []
        for sq in board.pieces(chess.KNIGHT, color):
            f = chess.square_file(sq)
            r = chess.square_rank(sq)

            # Check if in enemy half
            in_enemy_half = (r >= 4 if color == chess.WHITE else r <= 3)
            if not in_enemy_half:
                continue

            # Check if no enemy pawn can attack this square
            can_be_attacked = False
            adj_files = [af for af in [f - 1, f + 1] if 0 <= af <= 7]
            for ep in enemy_pawns:
                ef = chess.square_file(ep)
                er = chess.square_rank(ep)
                if ef in adj_files:
                    if color == chess.WHITE and er > r:
                        can_be_attacked = True
                        break
                    elif color == chess.BLACK and er < r:
                        can_be_attacked = True
                        break

            if not can_be_attacked:
                # Check if defended by own pawn
                defended_by_pawn = False
                own_pawns = board.pieces(chess.PAWN, color)
                for p in own_pawns:
                    if sq in board.attacks(p):
                        defended_by_pawn = True
                        break
                outposts.append({
                    "square": chess.square_name(sq),
                    "pawn_defended": defended_by_pawn,
                })

        # Bishop fianchetto
        fianchetto = []
        fianchetto_squares = {
            chess.WHITE: [chess.G2, chess.B2],
            chess.BLACK: [chess.G7, chess.B7],
        }
        for sq in fianchetto_squares[color]:
            piece = board.piece_at(sq)
            if piece and piece.piece_type == chess.BISHOP and piece.color == color:
                fianchetto.append(chess.square_name(sq))

        # Rook analysis
        rooks_on_open = []
        rooks_on_semi_open = []
        rooks_on_7th = []
        seventh_rank = 6 if color == chess.WHITE else 1

        for sq in board.pieces(chess.ROOK, color):
            f = chess.square_file(sq)
            r = chess.square_rank(sq)

            white_pawns_on_file = any(
                chess.square_file(p) == f for p in board.pieces(chess.PAWN, chess.WHITE)
            )
            black_pawns_on_file = any(
                chess.square_file(p) == f for p in board.pieces(chess.PAWN, chess.BLACK)
            )

            if not white_pawns_on_file and not black_pawns_on_file:
                rooks_on_open.append(chess.square_name(sq))
            elif color == chess.WHITE and not white_pawns_on_file:
                rooks_on_semi_open.append(chess.square_name(sq))
            elif color == chess.BLACK and not black_pawns_on_file:
                rooks_on_semi_open.append(chess.square_name(sq))

            if r == seventh_rank:
                rooks_on_7th.append(chess.square_name(sq))

        result[color_name] = {
            "squares_attacked": total_attacked,
            "center_control": center_control,
            "knight_outposts": outposts,
            "bishop_fianchetto": fianchetto,
            "rooks_on_open_files": rooks_on_open,
            "rooks_on_semi_open_files": rooks_on_semi_open,
            "rooks_on_7th_rank": rooks_on_7th,
        }

    return result


def analyze_files(board: chess.Board) -> dict:
    """Identify open and semi-open files."""
    white_pawns = board.pieces(chess.PAWN, chess.WHITE)
    black_pawns = board.pieces(chess.PAWN, chess.BLACK)

    white_pawn_files = {chess.square_file(sq) for sq in white_pawns}
    black_pawn_files = {chess.square_file(sq) for sq in black_pawns}

    file_names = "abcdefgh"
    open_files = []
    white_semi_open = []
    black_semi_open = []

    for f in range(8):
        w = f in white_pawn_files
        b = f in black_pawn_files
        if not w and not b:
            open_files.append(file_names[f])
        elif not w and b:
            white_semi_open.append(file_names[f])
        elif w and not b:
            black_semi_open.append(file_names[f])

    return {
        "open": open_files,
        "white_semi_open": white_semi_open,
        "black_semi_open": black_semi_open,
    }


def analyze_king_safety(board: chess.Board) -> dict:
    """Analyze king safety for both sides."""
    result = {}
    for color_name, color in [("white", chess.WHITE), ("black", chess.BLACK)]:
        king_sq = board.king(color)
        if king_sq is None:
            result[color_name] = {"error": "no king found"}
            continue

        king_file = chess.square_file(king_sq)
        king_rank = chess.square_rank(king_sq)

        # Castling rights
        can_castle_kingside = board.has_kingside_castling_rights(color)
        can_castle_queenside = board.has_queenside_castling_rights(color)
        has_castled = not can_castle_kingside and not can_castle_queenside and (
            (color == chess.WHITE and king_file in (6, 2)) or
            (color == chess.BLACK and king_file in (6, 2))
        )

        # Pawn shield: pawns on adjacent files and file of king, one rank ahead
        shield_rank = king_rank + (1 if color == chess.WHITE else -1)
        shield_files = [f for f in [king_file - 1, king_file, king_file + 1]
                        if 0 <= f <= 7]
        shield_pawns = []
        missing_shield = []
        for f in shield_files:
            if 0 <= shield_rank <= 7:
                sq = chess.square(f, shield_rank)
                piece = board.piece_at(sq)
                if piece and piece.piece_type == chess.PAWN and piece.color == color:
                    shield_pawns.append(chess.square_name(sq))
                else:
                    missing_shield.append(chess.square_name(chess.square(f, shield_rank)))

        # Attackers near king (within 2 squares)
        king_zone = set()
        for dr in range(-2, 3):
            for df in range(-2, 3):
                r, f = king_rank + dr, king_file + df
                if 0 <= r <= 7 and 0 <= f <= 7:
                    king_zone.add(chess.square(f, r))

        enemy = not color
        attackers = []
        defenders = []
        for sq in king_zone:
            piece = board.piece_at(sq)
            if piece and piece.piece_type != chess.KING:
                name = f"{PIECE_NAMES[piece.piece_type]} on {chess.square_name(sq)}"
                if piece.color == enemy:
                    attackers.append(name)
                elif piece.color == color:
                    defenders.append(name)

        result[color_name] = {
            "king_square": chess.square_name(king_sq),
            "can_castle_kingside": can_castle_kingside,
            "can_castle_queenside": can_castle_queenside,
            "likely_castled": has_castled,
            "pawn_shield": shield_pawns,
            "missing_shield": missing_shield,
            "nearby_attackers": attackers,
            "nearby_defenders": defenders,
        }

    return result


def analyze_space(board: chess.Board) -> dict:
    """Analyze space control — squares controlled beyond the 4th/5th rank."""
    result = {}
    for color_name, color in [("white", chess.WHITE), ("black", chess.BLACK)]:
        controlled = set()
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.color == color:
                for target in board.attacks(sq):
                    r = chess.square_rank(target)
                    if color == chess.WHITE and r >= 4:
                        controlled.add(target)
                    elif color == chess.BLACK and r <= 3:
                        controlled.add(target)

        # Pawn frontier — most advanced pawn rank
        pawns = board.pieces(chess.PAWN, color)
        if pawns:
            if color == chess.WHITE:
                frontier = max(chess.square_rank(sq) for sq in pawns)
            else:
                frontier = min(chess.square_rank(sq) for sq in pawns)
        else:
            frontier = None

        result[color_name] = {
            "squares_controlled_in_enemy_half": len(controlled),
            "controlled_squares": sorted(chess.square_name(sq) for sq in controlled),
            "pawn_frontier_rank": frontier + 1 if frontier is not None else None,
        }

    return result


def analyze_pins(board: chess.Board) -> list[dict]:
    """Detect all absolute pins (pinned to king)."""
    pins = []
    for color_name, color in [("white", chess.WHITE), ("black", chess.BLACK)]:
        king_sq = board.king(color)
        if king_sq is None:
            continue
        for sq in chess.SQUARES:
            if board.is_pinned(color, sq):
                piece = board.piece_at(sq)
                if piece and piece.color == color and piece.piece_type != chess.KING:
                    # Find the pinner
                    pin_mask = board.pin(color, sq)
                    pinner_sq = None
                    enemy = not color
                    for psq in chess.SQUARES:
                        ep = board.piece_at(psq)
                        if (ep and ep.color == enemy and
                                psq in chess.SquareSet(pin_mask) and psq != sq):
                            pinner_sq = psq
                            break
                    pins.append({
                        "pinned_piece": f"{PIECE_NAMES[piece.piece_type]} on {chess.square_name(sq)}",
                        "pinned_side": color_name,
                        "pinned_to": "king",
                        "pinner": (
                            f"{PIECE_NAMES[board.piece_at(pinner_sq).piece_type]} on {chess.square_name(pinner_sq)}"
                            if pinner_sq and board.piece_at(pinner_sq) else "unknown"
                        ),
                    })
    return pins


def analyze_development(board: chess.Board) -> dict:
    """Heuristic development analysis based on pieces on starting squares."""
    result = {}
    for color_name, color in [("white", chess.WHITE), ("black", chess.BLACK)]:
        undeveloped = []
        for pt in [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            for start_sq in STARTING_SQUARES[color][pt]:
                piece = board.piece_at(start_sq)
                if piece and piece.piece_type == pt and piece.color == color:
                    undeveloped.append(
                        f"{PIECE_NAMES[pt]} on {chess.square_name(start_sq)}"
                    )
        result[color_name] = {
            "pieces_on_starting_squares": undeveloped,
            "development_count": (
                len(STARTING_SQUARES[color][chess.KNIGHT]) +
                len(STARTING_SQUARES[color][chess.BISHOP]) +
                len(STARTING_SQUARES[color][chess.ROOK]) +
                len(STARTING_SQUARES[color][chess.QUEEN])
                - len(undeveloped)
            ),
            "total_developable": (
                len(STARTING_SQUARES[color][chess.KNIGHT]) +
                len(STARTING_SQUARES[color][chess.BISHOP]) +
                len(STARTING_SQUARES[color][chess.ROOK]) +
                len(STARTING_SQUARES[color][chess.QUEEN])
            ),
        }
    return result


def detect_game_phase(board: chess.Board) -> dict:
    """Heuristic game phase detection based on material."""
    total_non_pawn = 0
    queens = 0
    for color in [chess.WHITE, chess.BLACK]:
        for pt in [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            count = len(board.pieces(pt, color))
            total_non_pawn += count * PIECE_VALUES[pt]
            if pt == chess.QUEEN:
                queens += count

    if total_non_pawn >= 50:
        phase = "opening"
    elif total_non_pawn >= 24:
        phase = "middlegame"
    elif total_non_pawn >= 10:
        phase = "early_endgame"
    else:
        phase = "endgame"

    # Refine: if queens are off, skew toward endgame
    if queens == 0 and phase == "middlegame":
        phase = "early_endgame"

    return {
        "phase": phase,
        "total_non_pawn_material": total_non_pawn,
        "queens_on_board": queens,
    }


def get_legal_moves(board: chess.Board) -> list[str]:
    """Return all legal moves in SAN notation."""
    return sorted(board.san(m) for m in board.legal_moves)


def board_display(board: chess.Board) -> str:
    """Unicode board rendering."""
    return board.unicode(borders=True, empty_square="·")


# ── Superior Minor Piece ──────────────────────────────────────────────────────

def analyze_superior_minor_piece(board: chess.Board, material: dict,
                                  piece_activity: dict, pawn_structure: dict,
                                  files: dict, game_phase: dict,
                                  engine: dict | None = None) -> dict:
    """Assess minor piece quality: bishop pair, bad bishops, knight outposts."""
    total_pawns = (pawn_structure["white"]["pawn_count"]
                   + pawn_structure["black"]["pawn_count"])
    open_file_count = len(files["open"])

    if open_file_count >= 3 or total_pawns <= 10:
        position_type = "open"
    elif open_file_count <= 1 and total_pawns >= 14:
        position_type = "closed"
    else:
        position_type = "semi-open"

    phase = game_phase["phase"]
    sides = {}
    for color_name, color in [("white", chess.WHITE), ("black", chess.BLACK)]:
        bishops = list(board.pieces(chess.BISHOP, color))
        knights = list(board.pieces(chess.KNIGHT, color))
        has_pair = material[color_name]["bishop_pair"]

        # Bad bishops: own pawns on same color complex
        own_pawns = board.pieces(chess.PAWN, color)
        bad_bishops = []
        for bsq in bishops:
            bishop_light = (chess.square_rank(bsq) + chess.square_file(bsq)) % 2
            same_color_pawns = sum(
                1 for p in own_pawns
                if (chess.square_rank(p) + chess.square_file(p)) % 2 == bishop_light
            )
            total_own = len(own_pawns)
            if total_own > 0 and same_color_pawns / total_own > 0.5:
                bad_bishops.append(chess.square_name(bsq))

        # Good knights: reuse outpost data from piece_activity
        outposts = piece_activity[color_name]["knight_outposts"]
        good_knights = [
            {"square": o["square"], "pawn_defended": o["pawn_defended"]}
            for o in outposts
        ]

        # Score
        score = 0
        if has_pair:
            score += {"open": 2, "semi-open": 1, "closed": 0}[position_type]
            if phase in ("early_endgame", "endgame"):
                score += 1
        score -= len(bad_bishops)
        for gk in good_knights:
            if gk["pawn_defended"]:
                score += {"open": 0, "semi-open": 1, "closed": 2}[position_type]
            else:
                score += {"open": 0, "semi-open": 0, "closed": 1}[position_type]

        sides[color_name] = {
            "bishops": len(bishops),
            "knights": len(knights),
            "bishop_pair": has_pair,
            "bad_bishops": bad_bishops,
            "good_knights": good_knights,
            "minor_piece_score": score,
        }

    # Verdict
    diff = sides["white"]["minor_piece_score"] - sides["black"]["minor_piece_score"]
    if diff > 0:
        verdict = "white_better"
    elif diff < 0:
        verdict = "black_better"
    else:
        verdict = "equal"

    # Engine assessment
    engine_assessment = None
    if engine and engine.get("available") and engine.get("eval"):
        ev = engine["eval"]
        score_cp = ev.get("score_cp")
        if score_cp is not None:
            direction = "White" if score_cp > 0 else "Black"
            agrees = (score_cp > 0 and verdict == "white_better") or \
                     (score_cp < 0 and verdict == "black_better")
            sign = "+" if score_cp >= 0 else ""
            if verdict != "equal":
                if agrees:
                    engine_assessment = f"Engine confirms {direction}'s minor pieces are superior ({sign}{score_cp / 100:.2f})."
                else:
                    engine_assessment = f"Engine eval ({sign}{score_cp / 100:.2f}) suggests other factors outweigh minor piece assessment."

    return {
        "white": sides["white"],
        "black": sides["black"],
        "position_type": position_type,
        "verdict": verdict,
        "engine_assessment": engine_assessment,
    }


# ── Initiative ───────────────────────────────────────────────────────────────

def analyze_initiative(board: chess.Board, development: dict,
                       king_safety: dict, tactics: dict, pins: list,
                       piece_activity: dict,
                       engine: dict | None = None) -> dict:
    """Assess which side has the initiative: checks, captures, threats, pins."""
    sides = {}
    side_to_move = chess.WHITE if board.turn == chess.WHITE else chess.BLACK

    for color_name, color in [("white", chess.WHITE), ("black", chess.BLACK)]:
        opponent_name = "black" if color == chess.WHITE else "white"
        checks = 0
        captures = 0

        if color == side_to_move:
            for move in board.legal_moves:
                if board.gives_check(move):
                    checks += 1
                if board.is_capture(move):
                    captures += 1
        else:
            # Approximate from tactics threats for the non-moving side
            threats = tactics.get("threats", {})
            for key in threats:
                for t in threats[key]:
                    if isinstance(t, dict) and t.get("side") == color_name:
                        captures += 1

        # Threats count from tactics
        threat_count = 0
        for category in ("threats", "static"):
            section = tactics.get(category, {})
            for key in section:
                items = section[key]
                if isinstance(items, list):
                    for t in items:
                        if isinstance(t, dict) and t.get("side") == color_name:
                            threat_count += 1

        # Pins imposed (pinned_side is opponent)
        pins_imposed = sum(
            1 for p in pins if p.get("pinned_side") == opponent_name
        )

        # Development lead
        dev_self = development[color_name]["development_count"]
        dev_opp = development[opponent_name]["development_count"]
        dev_lead = max(0, dev_self - dev_opp)

        # Attackers near enemy king
        attackers_near_king = len(
            king_safety[opponent_name].get("nearby_attackers", [])
        )

        # Score: +2 per check, +1 per threat, +1 per pin, +1 per dev lead (cap 3),
        #        +1 per attacker near enemy king
        score = (checks * 2 + threat_count + pins_imposed
                 + min(dev_lead, 3) + attackers_near_king)

        sides[color_name] = {
            "checks_available": checks,
            "captures_available": captures,
            "threats_count": threat_count,
            "pins_imposed": pins_imposed,
            "development_lead": dev_lead,
            "attackers_near_enemy_king": attackers_near_king,
            "initiative_score": score,
        }

    # Determine side with initiative
    w_score = sides["white"]["initiative_score"]
    b_score = sides["black"]["initiative_score"]
    diff = w_score - b_score
    if diff >= 3:
        side_with = "white"
    elif diff <= -3:
        side_with = "black"
    else:
        side_with = "balanced"

    # Engine assessment
    engine_assessment = None
    if engine and engine.get("available") and engine.get("eval"):
        ev = engine["eval"]
        score_cp = ev.get("score_cp")
        wdl = ev.get("wdl")
        pv = ev.get("pv", [])
        if wdl and (wdl.get("win", 0) > 700 or wdl.get("loss", 0) > 700):
            dominant = "White" if wdl.get("win", 0) > 700 else "Black"
            pv_excerpt = " ".join(pv[:5]) if pv else ""
            engine_assessment = f"Engine's PV shows {dominant} maintaining pressure"
            if pv_excerpt:
                sign = "+" if (score_cp or 0) >= 0 else ""
                engine_assessment += f": {pv_excerpt} ({sign}{(score_cp or 0) / 100:.2f})."
            else:
                engine_assessment += "."

    return {
        "white": sides["white"],
        "black": sides["black"],
        "side_with_initiative": side_with,
        "engine_assessment": engine_assessment,
    }


# ── Statics vs Dynamics ─────────────────────────────────────────────────────

def analyze_statics_vs_dynamics(board: chess.Board, result: dict,
                                 engine: dict | None = None) -> dict:
    """Classify static vs dynamic advantages for both sides."""
    game_phase = result["game_phase"]
    pawn_structure = result["pawn_structure"]
    material = result["material"]
    files = result["files"]
    king_safety = result["king_safety"]
    development = result["development"]
    initiative = result["initiative"]
    smp = result["superior_minor_piece"]

    total_pawns = (pawn_structure["white"]["pawn_count"]
                   + pawn_structure["black"]["pawn_count"])
    open_file_count = len(files["open"])
    total_threats = (initiative["white"]["threats_count"]
                     + initiative["black"]["threats_count"])

    sides = {}
    for color_name in ["white", "black"]:
        static_adv = []
        static_weak = []
        dynamic_adv = []
        dynamic_weak = []
        opponent_name = "black" if color_name == "white" else "white"

        # Static advantages
        if material[color_name]["bishop_pair"]:
            static_adv.append("bishop pair")
        for p in pawn_structure[color_name].get("passed", []):
            static_adv.append(f"passed pawn on {p}")
        for o in smp[color_name]["good_knights"]:
            static_adv.append(f"knight outpost on {o['square']}")

        # Static weaknesses
        for p in pawn_structure[color_name].get("doubled", []):
            static_weak.append(f"doubled pawn on {p}")
        for p in pawn_structure[color_name].get("isolated", []):
            static_weak.append(f"isolated pawn on {p}")
        for p in pawn_structure[color_name].get("backward", []):
            static_weak.append(f"backward pawn on {p}")
        if king_safety[color_name].get("missing_shield"):
            ms = king_safety[color_name]["missing_shield"]
            if len(ms) >= 2:
                static_weak.append(f"weakened king shelter ({len(ms)} missing shield pawns)")

        # Dynamic advantages
        if initiative[color_name]["development_lead"] > 0:
            dynamic_adv.append("development lead")
        tc = initiative[color_name]["threats_count"]
        if tc >= 2:
            dynamic_adv.append(f"{tc} tactical threats")
        elif tc == 1:
            dynamic_adv.append("1 tactical threat")
        if initiative[color_name]["checks_available"] >= 2:
            dynamic_adv.append("multiple checks available")

        # Dynamic weaknesses
        ks = king_safety[color_name]
        if not ks.get("likely_castled") and not ks.get("can_castle_kingside") \
                and not ks.get("can_castle_queenside"):
            pass  # can't castle but maybe already safe
        elif not ks.get("likely_castled") and game_phase["phase"] in ("opening", "middlegame"):
            if ks.get("can_castle_kingside") or ks.get("can_castle_queenside"):
                dynamic_weak.append("king uncastled")

        # Scores
        static_score = len(static_adv) - len(static_weak)
        dynamic_score = len(dynamic_adv) - len(dynamic_weak)

        sides[color_name] = {
            "static_advantages": static_adv,
            "static_weaknesses": static_weak,
            "dynamic_advantages": dynamic_adv,
            "dynamic_weaknesses": dynamic_weak,
            "static_score": static_score,
            "dynamic_score": dynamic_score,
        }

    # Position character
    if total_pawns >= 14 and open_file_count <= 1 and total_threats <= 2:
        position_character = "static"
    elif open_file_count >= 3 or total_threats >= 5:
        position_character = "dynamic"
    else:
        position_character = "transitional"

    # Dominant factor
    w_static = sides["white"]["static_score"] - sides["black"]["static_score"]
    w_dynamic = sides["white"]["dynamic_score"] - sides["black"]["dynamic_score"]
    if abs(w_static) > abs(w_dynamic) + 1:
        dominant_factor = "statics"
    elif abs(w_dynamic) > abs(w_static) + 1:
        dominant_factor = "dynamics"
    else:
        dominant_factor = "balanced"

    # Compensation: one side has static deficit but dynamic surplus
    compensation = False
    for color_name in ["white", "black"]:
        s = sides[color_name]
        if s["static_score"] < 0 and s["dynamic_score"] > 0 and \
                s["dynamic_score"] >= abs(s["static_score"]):
            compensation = True
            break

    # Engine assessment
    engine_assessment = None
    if engine and engine.get("available") and engine.get("eval"):
        ev = engine["eval"]
        score_cp = ev.get("score_cp")
        if score_cp is not None:
            # Naive static estimate
            mat_balance = material["balance"] * 100
            bp_bonus = 50 if material["white"]["bishop_pair"] else 0
            bp_bonus -= 50 if material["black"]["bishop_pair"] else 0
            passed_bonus = len(pawn_structure["white"].get("passed", [])) * 30
            passed_bonus -= len(pawn_structure["black"].get("passed", [])) * 30
            weak_penalty = 0
            for side_name, sign in [("white", 1), ("black", -1)]:
                ps = pawn_structure[side_name]
                weak_penalty += sign * (
                    len(ps.get("doubled", [])) + len(ps.get("isolated", []))
                    + len(ps.get("backward", []))
                ) * 30
            static_est = mat_balance + bp_bonus + passed_bonus - weak_penalty

            discrepancy = abs(score_cp - static_est)
            if discrepancy > 75:
                sign = "+" if score_cp >= 0 else ""
                est_sign = "+" if static_est >= 0 else ""
                engine_assessment = (
                    f"Engine eval ({sign}{score_cp / 100:.2f}) exceeds static estimate "
                    f"({est_sign}{static_est / 100:.2f}) by {discrepancy}cp — "
                    f"dynamic factors provide significant compensation."
                )

    return {
        "white": sides["white"],
        "black": sides["black"],
        "position_character": position_character,
        "dominant_factor": dominant_factor,
        "compensation_detected": compensation,
        "engine_assessment": engine_assessment,
    }


# ── Main analysis ─────────────────────────────────────────────────────────────

def analyze_position(board: chess.Board, engine: EngineEval | None = None,
                     engine_depth: int = 20, engine_lines: int = 3) -> dict:
    """Full position analysis returning structured data.

    If engine is provided (and available), adds an 'engine' key with
    Stockfish evaluation, top lines, and WDL statistics.
    """
    result = {
        "fen": board.fen(),
        "side_to_move": "white" if board.turn == chess.WHITE else "black",
        "move_number": board.fullmove_number,
        "board_display": board_display(board),
        "material": analyze_material(board),
        "pawn_structure": analyze_pawn_structure(board),
        "piece_activity": analyze_piece_activity(board),
        "files": analyze_files(board),
        "king_safety": analyze_king_safety(board),
        "space": analyze_space(board),
        "pins": analyze_pins(board),
        "tactics": analyze_tactics(board),
        "development": analyze_development(board),
        "game_phase": detect_game_phase(board),
        "legal_moves": get_legal_moves(board),
        "is_check": board.is_check(),
        "is_checkmate": board.is_checkmate(),
        "is_stalemate": board.is_stalemate(),
    }

    # Engine evaluation (optional)
    if engine and engine.available:
        eval_result = engine.evaluate_position(board, depth=engine_depth)
        multipv = engine.evaluate_multipv(board, num_lines=engine_lines,
                                          depth=engine_depth)
        result["engine"] = {
            "eval": eval_result,
            "top_lines": multipv,
            "depth": engine_depth,
            "available": True,
        }
    else:
        result["engine"] = {"available": False}

    # Three additional imbalance assessments (depend on engine + prior analyzers)
    result["superior_minor_piece"] = analyze_superior_minor_piece(
        board, result["material"], result["piece_activity"],
        result["pawn_structure"], result["files"], result["game_phase"],
        engine=result.get("engine"),
    )
    result["initiative"] = analyze_initiative(
        board, result["development"], result["king_safety"],
        result["tactics"], result["pins"], result["piece_activity"],
        engine=result.get("engine"),
    )
    result["statics_vs_dynamics"] = analyze_statics_vs_dynamics(
        board, result, engine=result.get("engine"),
    )

    return result


def format_text(data: dict) -> str:
    """Human-readable text output from analysis data."""
    lines = []
    lines.append("=" * 50)
    lines.append("POSITION ANALYSIS")
    lines.append("=" * 50)
    lines.append("")
    lines.append(data["board_display"])
    lines.append("")
    lines.append(f"FEN: {data['fen']}")
    lines.append(f"Side to move: {data['side_to_move']}")
    lines.append(f"Move: {data['move_number']}")
    lines.append(f"Phase: {data['game_phase']['phase']}")
    lines.append("")

    # Material
    m = data["material"]
    lines.append("── Material ──")
    lines.append(f"  White: {m['white']['total_points']} pts  "
                 f"(P:{m['white']['pawns']} N:{m['white']['knights']} "
                 f"B:{m['white']['bishops']} R:{m['white']['rooks']} "
                 f"Q:{m['white']['queens']})"
                 f"{'  [Bishop pair]' if m['white']['bishop_pair'] else ''}")
    lines.append(f"  Black: {m['black']['total_points']} pts  "
                 f"(P:{m['black']['pawns']} N:{m['black']['knights']} "
                 f"B:{m['black']['bishops']} R:{m['black']['rooks']} "
                 f"Q:{m['black']['queens']})"
                 f"{'  [Bishop pair]' if m['black']['bishop_pair'] else ''}")
    lines.append(f"  Balance: {m['balance_description']}")
    lines.append("")

    # Pawn structure
    ps = data["pawn_structure"]
    lines.append("── Pawn Structure ──")
    for side in ["white", "black"]:
        s = ps[side]
        lines.append(f"  {side.capitalize()}:")
        if s["doubled"]:
            lines.append(f"    Doubled: {', '.join(s['doubled'])}")
        if s["isolated"]:
            lines.append(f"    Isolated: {', '.join(s['isolated'])}")
        if s["backward"]:
            lines.append(f"    Backward: {', '.join(s['backward'])}")
        if s["passed"]:
            lines.append(f"    Passed: {', '.join(s['passed'])}")
        lines.append(f"    Islands: {s['pawn_islands']}")
        if s["chain_bases"]:
            lines.append(f"    Chain bases: {', '.join(s['chain_bases'])}")
    lines.append("")

    # Piece activity
    pa = data["piece_activity"]
    lines.append("── Piece Activity ──")
    for side in ["white", "black"]:
        a = pa[side]
        lines.append(f"  {side.capitalize()}:")
        lines.append(f"    Squares attacked: {a['squares_attacked']}")
        lines.append(f"    Center control: {', '.join(a['center_control']) or 'none'}")
        if a["knight_outposts"]:
            outpost_strs = [
                f"{o['square']}{'(pawn-defended)' if o['pawn_defended'] else ''}"
                for o in a["knight_outposts"]
            ]
            lines.append(f"    Knight outposts: {', '.join(outpost_strs)}")
        if a["bishop_fianchetto"]:
            lines.append(f"    Fianchettoed bishop: {', '.join(a['bishop_fianchetto'])}")
        if a["rooks_on_open_files"]:
            lines.append(f"    Rooks on open files: {', '.join(a['rooks_on_open_files'])}")
        if a["rooks_on_semi_open_files"]:
            lines.append(f"    Rooks on semi-open files: {', '.join(a['rooks_on_semi_open_files'])}")
        if a["rooks_on_7th_rank"]:
            lines.append(f"    Rooks on 7th: {', '.join(a['rooks_on_7th_rank'])}")
    lines.append("")

    # Files
    fi = data["files"]
    lines.append("── Files ──")
    lines.append(f"  Open: {', '.join(fi['open']) or 'none'}")
    lines.append(f"  White semi-open: {', '.join(fi['white_semi_open']) or 'none'}")
    lines.append(f"  Black semi-open: {', '.join(fi['black_semi_open']) or 'none'}")
    lines.append("")

    # King safety
    ks = data["king_safety"]
    lines.append("── King Safety ──")
    for side in ["white", "black"]:
        k = ks[side]
        lines.append(f"  {side.capitalize()} king on {k['king_square']}:")
        castle_parts = []
        if k["can_castle_kingside"]:
            castle_parts.append("O-O")
        if k["can_castle_queenside"]:
            castle_parts.append("O-O-O")
        if k["likely_castled"]:
            castle_parts.append("(already castled)")
        lines.append(f"    Castling: {' '.join(castle_parts) or 'none'}")
        if k["pawn_shield"]:
            lines.append(f"    Pawn shield: {', '.join(k['pawn_shield'])}")
        if k["missing_shield"]:
            lines.append(f"    Missing shield: {', '.join(k['missing_shield'])}")
        if k["nearby_attackers"]:
            lines.append(f"    Nearby attackers: {', '.join(k['nearby_attackers'])}")
    lines.append("")

    # Space
    sp = data["space"]
    lines.append("── Space ──")
    for side in ["white", "black"]:
        s = sp[side]
        lines.append(f"  {side.capitalize()}: {s['squares_controlled_in_enemy_half']} squares in enemy half"
                     f"  (frontier rank {s['pawn_frontier_rank']})")
    lines.append("")

    # Pins
    if data["pins"]:
        lines.append("── Pins ──")
        for p in data["pins"]:
            lines.append(f"  {p['pinned_piece']} pinned by {p['pinner']}")
        lines.append("")

    # Tactics
    if "tactics" in data:
        tac = data["tactics"]
        has_tactics = False
        tac_lines = ["── Tactics ──"]

        # Static
        static = tac.get("static", {})
        if static.get("pins"):
            for p in static["pins"]:
                tac_lines.append(f"  Pin ({p['pin_type']}): {p['pinned_piece']} pinned to {p['pinned_to']} by {p['pinner']}")
            has_tactics = True
        if static.get("batteries"):
            for b in static["batteries"]:
                tac_lines.append(f"  Battery: {', '.join(b['pieces'])} on {b['line']} [{b['side']}]")
            has_tactics = True
        if static.get("hanging_pieces"):
            for h in static["hanging_pieces"]:
                tac_lines.append(f"  Hanging: {h['piece']} ({h['type']}) [{h['side']}]")
            has_tactics = True
        if static.get("overloaded_pieces"):
            for o in static["overloaded_pieces"]:
                tac_lines.append(f"  Overloaded: {o['piece']} guarding {', '.join(o['guarding'])} [{o['side']}]")
            has_tactics = True
        for side_name in ["white", "black"]:
            wbr = static.get("weak_back_rank", {}).get(side_name, {})
            if wbr.get("is_weak"):
                tac_lines.append(f"  Weak back rank: {side_name}")
                has_tactics = True
        if static.get("trapped_pieces"):
            for t in static["trapped_pieces"]:
                tac_lines.append(f"  Trapped: {t['piece']} [{t['side']}]")
            has_tactics = True
        if static.get("advanced_passed_pawns"):
            for a in static["advanced_passed_pawns"]:
                prot = " (protected)" if a["is_protected"] else ""
                tac_lines.append(f"  Advanced passed pawn: {a['square']} rank {a['rank']}{prot} [{a['side']}]")
            has_tactics = True
        if static.get("xray_attacks"):
            for x in static["xray_attacks"]:
                tac_lines.append(f"  X-ray: {x['attacker']} through {x['through']} to {x['target']} [{x['side']}]")
            has_tactics = True
        if static.get("alignments"):
            for a in static["alignments"]:
                tac_lines.append(f"  Alignment: {', '.join(a['pieces'])} on {a['line']} (potential {a['potential']}) [{a['side']}]")
            has_tactics = True

        # Threats
        threats = tac.get("threats", {})
        if threats.get("forks"):
            for f in threats["forks"]:
                tac_lines.append(f"  Fork: {f['move']} ({f['forking_piece']} attacks {', '.join(f['targets'])}) [{f['side']}]")
            has_tactics = True
        if threats.get("skewers"):
            for s in threats["skewers"]:
                tac_lines.append(f"  Skewer: {s['move']} ({s['skewering_piece']} through {s['front_target']} to {s['rear_target']}) [{s['side']}]")
            has_tactics = True
        if threats.get("discovered_attacks"):
            for d in threats["discovered_attacks"]:
                tac_lines.append(f"  Discovered attack: {d['move']} reveals {d['revealed_attacker']} on {d['target']} [{d['side']}]")
            has_tactics = True
        if threats.get("discovered_checks"):
            for d in threats["discovered_checks"]:
                tac_lines.append(f"  Discovered check: {d['move']} reveals {d['checking_piece']} [{d['side']}]")
            has_tactics = True
        if threats.get("double_checks"):
            for d in threats["double_checks"]:
                tac_lines.append(f"  Double check: {d['move']} ({', '.join(d['checkers'])}) [{d['side']}]")
            has_tactics = True
        if threats.get("back_rank_mates"):
            for m in threats["back_rank_mates"]:
                tac_lines.append(f"  Back rank mate: {m['move']} [{m['side']}]")
            has_tactics = True
        if threats.get("removal_of_guard"):
            for r in threats["removal_of_guard"]:
                tac_lines.append(f"  Removal of guard: {r['move']} captures {r['captured_guard']}, exposes {r['exposed_piece']} [{r['side']}]")
            has_tactics = True

        # Sequences
        seqs = tac.get("sequences", {})
        if seqs.get("deflections"):
            for d in seqs["deflections"]:
                tac_lines.append(f"  Deflection: {d['forcing_move']} → {d['followup']} [{d['side']}]")
            has_tactics = True
        if seqs.get("zwischenzug"):
            for z in seqs["zwischenzug"]:
                tac_lines.append(f"  Zwischenzug: after {z['capture']}, {z['zwischenzug_move']} [{z['side']}]")
            has_tactics = True
        if seqs.get("smothered_mates"):
            for s in seqs["smothered_mates"]:
                if "move" in s:
                    tac_lines.append(f"  Smothered mate: {s['move']} [{s['side']}]")
                elif "sequence" in s:
                    tac_lines.append(f"  Smothered mate: {' → '.join(s['sequence'])} [{s['side']}]")
            has_tactics = True

        if has_tactics:
            lines.extend(tac_lines)
            lines.append("")

    # Development
    dev = data["development"]
    lines.append("── Development ──")
    for side in ["white", "black"]:
        d = dev[side]
        lines.append(f"  {side.capitalize()}: {d['development_count']}/{d['total_developable']} pieces developed")
        if d["pieces_on_starting_squares"]:
            lines.append(f"    Still home: {', '.join(d['pieces_on_starting_squares'])}")
    lines.append("")

    # Superior Minor Piece
    if "superior_minor_piece" in data:
        smp = data["superior_minor_piece"]
        lines.append("── Superior Minor Piece ──")
        lines.append(f"  Position type: {smp['position_type']}")
        for side in ["white", "black"]:
            s = smp[side]
            parts = [f"{s['bishops']}B {s['knights']}N"]
            if s["bishop_pair"]:
                parts.append("bishop pair")
            if s["bad_bishops"]:
                parts.append(f"bad bishop(s): {', '.join(s['bad_bishops'])}")
            if s["good_knights"]:
                gk_strs = [f"{g['square']}{'(pawn)' if g['pawn_defended'] else ''}"
                           for g in s["good_knights"]]
                parts.append(f"outpost(s): {', '.join(gk_strs)}")
            lines.append(f"  {side.capitalize()}: {'; '.join(parts)}  [score: {s['minor_piece_score']}]")
        lines.append(f"  Verdict: {smp['verdict']}")
        if smp.get("engine_assessment"):
            lines.append(f"  Engine: {smp['engine_assessment']}")
        lines.append("")

    # Initiative
    if "initiative" in data:
        init = data["initiative"]
        lines.append("── Initiative ──")
        for side in ["white", "black"]:
            s = init[side]
            parts = []
            if s["checks_available"]:
                parts.append(f"{s['checks_available']} checks")
            if s["captures_available"]:
                parts.append(f"{s['captures_available']} captures")
            if s["threats_count"]:
                parts.append(f"{s['threats_count']} threats")
            if s["pins_imposed"]:
                parts.append(f"{s['pins_imposed']} pins imposed")
            if s["development_lead"]:
                parts.append(f"+{s['development_lead']} dev lead")
            if s["attackers_near_enemy_king"]:
                parts.append(f"{s['attackers_near_enemy_king']} attackers near king")
            desc = "; ".join(parts) if parts else "no dynamic pressure"
            lines.append(f"  {side.capitalize()}: {desc}  [score: {s['initiative_score']}]")
        lines.append(f"  Initiative: {init['side_with_initiative']}")
        if init.get("engine_assessment"):
            lines.append(f"  Engine: {init['engine_assessment']}")
        lines.append("")

    # Statics vs Dynamics
    if "statics_vs_dynamics" in data:
        svd = data["statics_vs_dynamics"]
        lines.append("── Statics vs Dynamics ──")
        lines.append(f"  Position character: {svd['position_character']}")
        for side in ["white", "black"]:
            s = svd[side]
            lines.append(f"  {side.capitalize()}:")
            if s["static_advantages"]:
                lines.append(f"    Static +: {', '.join(s['static_advantages'])}")
            if s["static_weaknesses"]:
                lines.append(f"    Static -: {', '.join(s['static_weaknesses'])}")
            if s["dynamic_advantages"]:
                lines.append(f"    Dynamic +: {', '.join(s['dynamic_advantages'])}")
            if s["dynamic_weaknesses"]:
                lines.append(f"    Dynamic -: {', '.join(s['dynamic_weaknesses'])}")
        lines.append(f"  Dominant factor: {svd['dominant_factor']}")
        if svd["compensation_detected"]:
            lines.append("  ⚡ Compensation detected")
        if svd.get("engine_assessment"):
            lines.append(f"  Engine: {svd['engine_assessment']}")
        lines.append("")

    # Engine evaluation
    eng = data.get("engine", {})
    if eng.get("available") and eng.get("eval"):
        ev = eng["eval"]
        lines.append("── Engine ──")
        score_str = ev["score_display"]
        if ev["mate_in"] is not None:
            lines.append(f"  Evaluation: {score_str} (mate in {abs(ev['mate_in'])})")
        else:
            lines.append(f"  Evaluation: {score_str}")
        if ev.get("wdl"):
            w, d, l = ev["wdl"]["win"], ev["wdl"]["draw"], ev["wdl"]["loss"]
            lines.append(f"  WDL: {w/10:.1f}% / {d/10:.1f}% / {l/10:.1f}%")
        lines.append(f"  Best move: {ev['best_move']}")
        if ev.get("pv"):
            lines.append(f"  PV: {' '.join(ev['pv'][:8])}")

        top = eng.get("top_lines")
        if top and len(top) > 1:
            lines.append(f"  Top {len(top)} lines:")
            for i, line in enumerate(top, 1):
                pv_str = " ".join(line.get("pv", [])[:6])
                lines.append(f"    {i}. ({line['score_display']}) {pv_str}")
        lines.append(f"  Depth: {eng.get('depth', '?')}")
        lines.append("")

    # Status
    if data["is_checkmate"]:
        lines.append("*** CHECKMATE ***")
    elif data["is_stalemate"]:
        lines.append("*** STALEMATE ***")
    elif data["is_check"]:
        lines.append(f"*** {data['side_to_move'].upper()} IS IN CHECK ***")

    lines.append(f"\nLegal moves ({len(data['legal_moves'])}): {', '.join(data['legal_moves'][:20])}")
    if len(data["legal_moves"]) > 20:
        lines.append(f"  ... and {len(data['legal_moves']) - 20} more")

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Analyze a chess position from FEN, PGN file, or move list."
    )
    parser.add_argument("position", help="FEN string, PGN file path, or move list")
    parser.add_argument("--format", choices=["json", "text"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--move", default=None,
                        help="Move number to analyze, e.g. '15' (after White's 15th) "
                             "or '15b' (after Black's 15th). PGN and move-list only.")
    parser.add_argument("--engine", action="store_true", default=False,
                        help="Enable Stockfish engine evaluation")
    parser.add_argument("--depth", type=int, default=20,
                        help="Engine search depth (default: 20)")
    parser.add_argument("--lines", type=int, default=3,
                        help="Number of engine lines to show (default: 3)")
    args = parser.parse_args()

    try:
        input_type, board = detect_input(args.position, args.move)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    engine = None
    if args.engine:
        engine = EngineEval()
        engine.open()
        if not engine.available:
            print("Warning: Stockfish not found, engine evaluation disabled",
                  file=sys.stderr)
            engine = None

    try:
        data = analyze_position(board, engine=engine,
                                engine_depth=args.depth, engine_lines=args.lines)
        data["input_type"] = input_type

        if args.format == "text":
            print(format_text(data))
        else:
            print(json.dumps(data, indent=2))
    finally:
        if engine:
            engine.close()


if __name__ == "__main__":
    main()
