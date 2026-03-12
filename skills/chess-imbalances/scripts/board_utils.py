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
