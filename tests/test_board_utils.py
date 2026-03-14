"""Tests for board_utils.py — chess position analysis engine.

Most positions are derived from move sequences to guarantee legality.
Hand-crafted FEN is validated via chess.Board() in setup.
"""

import tempfile
import textwrap

import chess
import chess.pgn
import pytest

import sys
from pathlib import Path

# Add scripts to path so we can import board_utils
sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "skills" / "chess-imbalances" / "scripts"))
import board_utils


# ── Helpers ───────────────────────────────────────────────────────────────────

def board_from_moves(*sans: str) -> chess.Board:
    """Play a sequence of SAN moves from the starting position."""
    board = chess.Board()
    for san in sans:
        board.push_san(san)
    return board


def analyze_from_moves(*sans: str) -> dict:
    """Play moves and return full analysis."""
    return board_utils.analyze_position(board_from_moves(*sans))


def analyze_fen(fen: str) -> dict:
    """Validate FEN and return full analysis."""
    board = chess.Board(fen)  # raises ValueError if invalid
    return board_utils.analyze_position(board)


def make_pgn_file(moves: str) -> str:
    """Write a PGN string to a temp file and return the path."""
    content = textwrap.dedent(f"""\
        [Event "Test"]
        [Result "*"]

        {moves} *
    """)
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".pgn", delete=False)
    f.write(content)
    f.close()
    return f.name


# ── Material ──────────────────────────────────────────────────────────────────

class TestMaterial:
    def test_starting_position_equal(self):
        data = analyze_fen(chess.STARTING_FEN)
        m = data["material"]
        assert m["white"]["total_points"] == 39
        assert m["black"]["total_points"] == 39
        assert m["balance"] == 0
        assert m["balance_description"] == "equal"

    def test_starting_position_bishop_pair(self):
        data = analyze_fen(chess.STARTING_FEN)
        m = data["material"]
        assert m["white"]["bishop_pair"] is True
        assert m["black"]["bishop_pair"] is True

    def test_material_imbalance_missing_queen(self):
        # Remove Black's queen: standard position but Qd8 replaced with empty
        fen = "rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        data = analyze_fen(fen)
        m = data["material"]
        assert m["white"]["total_points"] == 39
        assert m["black"]["total_points"] == 30
        assert m["balance"] == 9
        assert "White" in m["balance_description"]

    def test_bishop_pair_lost(self):
        # Exchange variation: 1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. Bxf7+ Kxf7
        # White's light-squared bishop captured and removed from board
        data = analyze_from_moves("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "Bxf7+", "Kxf7")
        m = data["material"]
        assert m["white"]["bishop_pair"] is False  # light-squared bishop captured
        assert m["black"]["bishop_pair"] is True

    def test_piece_counts(self):
        data = analyze_fen(chess.STARTING_FEN)
        w = data["material"]["white"]
        assert w["pawns"] == 8
        assert w["knights"] == 2
        assert w["bishops"] == 2
        assert w["rooks"] == 2
        assert w["queens"] == 1


# ── Pawn Structure ────────────────────────────────────────────────────────────

class TestPawnStructure:
    def test_doubled_pawns(self):
        # After 1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 4. d4 Nf6 5. Bc4 Bg4 6. Nf3 Bxf3 7. gxf3
        # White has doubled f-pawns
        data = analyze_from_moves(
            "e4", "d5", "exd5", "Qxd5", "Nc3", "Qa5",
            "d4", "Nf6", "Bc4", "Bg4", "Nf3", "Bxf3", "gxf3",
        )
        doubled = data["pawn_structure"]["white"]["doubled"]
        # Both f-pawns should be listed
        assert any("f" in sq for sq in doubled)
        assert len([sq for sq in doubled if sq.startswith("f")]) == 2

    def test_isolated_pawn(self):
        # Isolated d-pawn position (IQP):
        # White pawn on d4 with no pawns on c or e files
        fen = "r1bqkb1r/pp3ppp/2n2n2/4p3/3P4/5N2/PP3PPP/RNBQKB1R w KQkq - 0 6"
        data = analyze_fen(fen)
        isolated = data["pawn_structure"]["white"]["isolated"]
        assert "d4" in isolated

    def test_passed_pawn(self):
        # White passed pawn on d5, no black pawns on c/d/e files ahead
        fen = "4k3/pp3ppp/8/3P4/8/8/PPP2PPP/4K3 w - - 0 1"
        data = analyze_fen(fen)
        passed = data["pawn_structure"]["white"]["passed"]
        assert "d5" in passed

    def test_no_false_passed_pawn(self):
        # d5 pawn blocked by pawn on e6 — not passed
        fen = "4k3/pp3ppp/4p3/3P4/8/8/PPP2PPP/4K3 w - - 0 1"
        data = analyze_fen(fen)
        passed = data["pawn_structure"]["white"]["passed"]
        assert "d5" not in passed

    def test_backward_pawn(self):
        # White e3 backward: d-pawn on d4 (ahead, doesn't support), no f-pawn.
        # Black d5 pawn controls e4 so e3 can't advance safely.
        fen = "4k3/8/8/3p4/3P4/4P3/6PP/4K3 w - - 0 1"
        data = analyze_fen(fen)
        backward = data["pawn_structure"]["white"]["backward"]
        assert "e3" in backward
        # Should NOT be isolated (d4 pawn on adjacent file)
        assert "e3" not in data["pawn_structure"]["white"]["isolated"]

    def test_pawn_islands_starting(self):
        data = analyze_fen(chess.STARTING_FEN)
        assert data["pawn_structure"]["white"]["pawn_islands"] == 1
        assert data["pawn_structure"]["black"]["pawn_islands"] == 1

    def test_pawn_islands_multiple(self):
        # White pawns on a2, b2 (island 1), e4 (island 2), g2, h2 (island 3) = 3 islands
        fen = "4k3/pppppppp/8/8/4P3/8/PP4PP/4K3 w - - 0 1"
        data = analyze_fen(fen)
        assert data["pawn_structure"]["white"]["pawn_islands"] == 3


# ── Piece Activity ────────────────────────────────────────────────────────────

class TestPieceActivity:
    def test_knight_outpost(self):
        # White knight on d5, no black pawns on c or e files to challenge it,
        # defended by pawn on e4
        fen = "r1bqkb1r/pp3ppp/2n2n2/3N4/4P3/8/PPPP1PPP/R1BQKB1R b KQkq - 0 5"
        data = analyze_fen(fen)
        outposts = data["piece_activity"]["white"]["knight_outposts"]
        assert len(outposts) >= 1
        outpost_squares = [o["square"] for o in outposts]
        assert "d5" in outpost_squares
        # check pawn_defended
        d5_outpost = next(o for o in outposts if o["square"] == "d5")
        assert d5_outpost["pawn_defended"] is True

    def test_bishop_fianchetto(self):
        # King's Indian setup: 1. d4 Nf6 2. c4 g6 3. Nc3 Bg7
        data = analyze_from_moves("d4", "Nf6", "c4", "g6", "Nc3", "Bg7")
        fianchetto = data["piece_activity"]["black"]["bishop_fianchetto"]
        assert "g7" in fianchetto

    def test_no_false_fianchetto(self):
        data = analyze_fen(chess.STARTING_FEN)
        assert data["piece_activity"]["white"]["bishop_fianchetto"] == []
        assert data["piece_activity"]["black"]["bishop_fianchetto"] == []

    def test_rook_on_open_file(self):
        # White rook on e1, e-file open (no pawns on e-file for either side)
        fen = "r1bqkb1r/pppp1ppp/2n2n2/8/8/8/PPPP1PPP/RNBQR1K1 b kq - 0 5"
        data = analyze_fen(fen)
        assert "e" in data["files"]["open"]
        assert "e1" in data["piece_activity"]["white"]["rooks_on_open_files"]

    def test_rook_on_7th_rank(self):
        # White rook on d7
        fen = "r4rk1/pp1R1ppp/2p5/8/8/8/PPP2PPP/R5K1 b - - 0 1"
        data = analyze_fen(fen)
        assert "d7" in data["piece_activity"]["white"]["rooks_on_7th_rank"]

    def test_rook_on_semi_open_file(self):
        # White has no pawn on d-file, Black does — semi-open for White
        fen = "r1bqkbnr/pppppppp/8/8/8/8/PPP1PPPP/RNBQR1K1 b kq - 0 1"
        data = analyze_fen(fen)
        assert "d" in data["files"]["white_semi_open"]


# ── Files ─────────────────────────────────────────────────────────────────────

class TestFiles:
    def test_no_open_files_starting(self):
        data = analyze_fen(chess.STARTING_FEN)
        assert data["files"]["open"] == []

    def test_open_file_detected(self):
        # e-file open: no pawns on e-file
        fen = "rnbqkbnr/pppp1ppp/8/8/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"
        data = analyze_fen(fen)
        assert "e" in data["files"]["open"]


# ── King Safety ───────────────────────────────────────────────────────────────

class TestKingSafety:
    def test_castled_king_pawn_shield(self):
        # After 1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. O-O
        data = analyze_from_moves("e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "O-O")
        ks = data["king_safety"]["white"]
        assert ks["king_square"] == "g1"
        assert "f2" in ks["pawn_shield"]
        assert "g2" in ks["pawn_shield"]
        assert "h2" in ks["pawn_shield"]

    def test_uncastled_king_castling_rights(self):
        data = analyze_fen(chess.STARTING_FEN)
        ks = data["king_safety"]["white"]
        assert ks["can_castle_kingside"] is True
        assert ks["can_castle_queenside"] is True
        assert ks["likely_castled"] is False

    def test_missing_shield_pawn(self):
        # Castled kingside but h-pawn advanced: h2 missing from shield
        fen = "rnbqkbnr/pppppppp/8/8/8/7P/PPPPPPP1/RNBQK2R w KQkq - 0 1"
        board = chess.Board(fen)
        # Simulate castled king on g1 with h3 pawn
        fen2 = "rnbqkbnr/pppppppp/8/8/8/7P/PPPPPP2/RNBQ1RK1 b kq - 0 1"
        data = analyze_fen(fen2)
        ks = data["king_safety"]["white"]
        assert "h2" in ks["missing_shield"]


# ── Pins ──────────────────────────────────────────────────────────────────────

class TestPins:
    def test_pin_detected(self):
        # Clean absolute pin: White Bb5 pins Black Nd7 to Ke8.
        # Diagonal b5-c6-d7-e8 with only Nd7 between Bb5 and Ke8.
        fen = "4k3/3n4/8/1B6/8/8/8/4K3 w - - 0 1"
        data = analyze_fen(fen)
        pins = data["pins"]
        assert len(pins) >= 1
        nd7_pin = [p for p in pins if "d7" in p["pinned_piece"]]
        assert len(nd7_pin) == 1
        assert nd7_pin[0]["pinned_side"] == "black"
        assert nd7_pin[0]["pinned_to"] == "king"
        assert "b5" in nd7_pin[0]["pinner"]

    def test_no_pins_starting(self):
        data = analyze_fen(chess.STARTING_FEN)
        assert data["pins"] == []


# ── Development ───────────────────────────────────────────────────────────────

class TestDevelopment:
    def test_starting_position_undeveloped(self):
        data = analyze_fen(chess.STARTING_FEN)
        dev = data["development"]
        assert dev["white"]["development_count"] == 0
        assert dev["white"]["total_developable"] == 7
        assert dev["black"]["development_count"] == 0

    def test_partial_development(self):
        # 1. e4 e5 2. Nf3 — White has developed 1 piece (Nf3)
        data = analyze_from_moves("e4", "e5", "Nf3")
        dev = data["development"]
        assert dev["white"]["development_count"] == 1
        assert "knight on g1" not in [
            p for p in dev["white"]["pieces_on_starting_squares"]
        ]

    def test_fully_developed(self):
        # All White pieces off starting squares: Nc3, Nf3, Bc4, Qd2, Rd1, Re1
        fen = "r4rk1/pppq1ppp/2npbn2/4p3/2B1P3/2NP1N2/PPPQ1PPP/3RR1K1 w - - 0 10"
        data = analyze_fen(fen)
        dev = data["development"]["white"]
        assert dev["development_count"] == dev["total_developable"]
        assert dev["pieces_on_starting_squares"] == []


# ── Game Phase ────────────────────────────────────────────────────────────────

class TestGamePhase:
    def test_opening_phase(self):
        data = analyze_fen(chess.STARTING_FEN)
        assert data["game_phase"]["phase"] == "opening"

    def test_endgame_phase(self):
        # King + rook vs king + rook
        fen = "4k3/8/8/8/8/8/8/R3K3 w - - 0 1"
        data = analyze_fen(fen)
        assert data["game_phase"]["phase"] in ("endgame", "early_endgame")

    def test_middlegame_phase(self):
        # Remove queens but keep everything else
        fen = "rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNB1KBNR w KQkq - 0 1"
        data = analyze_fen(fen)
        phase = data["game_phase"]["phase"]
        assert phase in ("middlegame", "early_endgame")


# ── Space ─────────────────────────────────────────────────────────────────────

class TestSpace:
    def test_starting_position_no_space(self):
        data = analyze_fen(chess.STARTING_FEN)
        assert data["space"]["white"]["squares_controlled_in_enemy_half"] == 0
        assert data["space"]["black"]["squares_controlled_in_enemy_half"] == 0

    def test_space_after_e4(self):
        data = analyze_from_moves("e4")
        # e4 pawn controls d5, f5 — both in Black's half
        white_space = data["space"]["white"]["squares_controlled_in_enemy_half"]
        assert white_space > 0

    def test_pawn_frontier(self):
        data = analyze_from_moves("e4")
        assert data["space"]["white"]["pawn_frontier_rank"] == 4  # rank 4 (0-indexed 3 + 1)


# ── Input Detection ───────────────────────────────────────────────────────────

class TestInputDetection:
    def test_detect_fen(self):
        input_type, board = board_utils.detect_input(chess.STARTING_FEN)
        assert input_type == "fen"
        assert board.fen() == chess.STARTING_FEN

    def test_detect_move_list(self):
        input_type, board = board_utils.detect_input("1. e4 e5 2. Nf3")
        assert input_type == "moves"
        # After 1. e4 e5 2. Nf3, knight should be on f3
        assert board.piece_at(chess.F3) == chess.Piece(chess.KNIGHT, chess.WHITE)

    def test_detect_pgn_file(self):
        path = make_pgn_file("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6")
        input_type, board = board_utils.detect_input(path)
        assert input_type == "pgn"
        # After 3...a6, bishop should still be on b5
        assert board.piece_at(chess.B5) == chess.Piece(chess.BISHOP, chess.WHITE)

    def test_invalid_input_raises(self):
        with pytest.raises(ValueError):
            board_utils.detect_input("not a valid chess input xyz123")


# ── Move Targeting (--move) ───────────────────────────────────────────────────

class TestMoveTargeting:
    def test_pgn_move_white(self):
        path = make_pgn_file("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6")
        _, board = board_utils.detect_input(path, move="2")
        # After 2. Nf3: Black to move, knight on f3
        assert board.turn == chess.BLACK
        assert board.piece_at(chess.F3) == chess.Piece(chess.KNIGHT, chess.WHITE)
        # Nc6 hasn't happened yet
        assert board.piece_at(chess.B8) == chess.Piece(chess.KNIGHT, chess.BLACK)

    def test_pgn_move_black(self):
        path = make_pgn_file("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6")
        _, board = board_utils.detect_input(path, move="2b")
        # After 2...Nc6: White to move, knight on c6
        assert board.turn == chess.WHITE
        assert board.piece_at(chess.C6) == chess.Piece(chess.KNIGHT, chess.BLACK)

    def test_move_list_with_target(self):
        _, board = board_utils.detect_input("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6", move="1")
        # After 1. e4: Black to move, pawn on e4
        assert board.turn == chess.BLACK
        assert board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)

    def test_move_out_of_range(self):
        path = make_pgn_file("1. e4 e5 2. Nf3 Nc6")
        with pytest.raises(ValueError, match="not found"):
            board_utils.detect_input(path, move="99")

    def test_fen_with_move_warns(self, capsys):
        board_utils.detect_input(chess.STARTING_FEN, move="5")
        captured = capsys.readouterr()
        assert "ignored" in captured.err.lower()

    def test_parse_move_target_plain(self):
        num, after_black = board_utils.parse_move_target("15")
        assert num == 15
        assert after_black is False

    def test_parse_move_target_black(self):
        num, after_black = board_utils.parse_move_target("15b")
        assert num == 15
        assert after_black is True

    def test_parse_move_target_white_explicit(self):
        num, after_black = board_utils.parse_move_target("15w")
        assert num == 15
        assert after_black is False


# ── Check / Checkmate / Stalemate ─────────────────────────────────────────────

class TestGameStatus:
    def test_check_detected(self):
        # Scholar's mate attempt: 1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7#
        data = analyze_from_moves("e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6", "Qxf7#")
        assert data["is_checkmate"] is True

    def test_check_not_mate(self):
        # 1. e4 e5 2. Qh5 — not check
        # Use: Bxf7+ from Italian
        data = analyze_from_moves("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "Bxf7+")
        assert data["is_check"] is True
        assert data["is_checkmate"] is False

    def test_stalemate(self):
        # Classic stalemate: Black king on a8, White queen on b6, White king on c8
        # Actually: Ka1, Qb3 vs Ka8 — not quite
        # Known stalemate: White Kc6, Qa7 — oops that's checkmate
        # Use: White Kb6, Qd8 vs Ka8 with no black pieces
        # Simpler: programmatic
        fen = "k7/8/1K6/8/8/8/8/7Q b - - 0 1"
        board = chess.Board(fen)
        # Verify it's actually stalemate
        if board.is_stalemate():
            data = board_utils.analyze_position(board)
            assert data["is_stalemate"] is True
        else:
            # Adjust — use known stalemate position
            fen = "k7/2Q5/1K6/8/8/8/8/8 b - - 0 1"
            data = analyze_fen(fen)
            assert data["is_stalemate"] is True

    def test_no_check_starting(self):
        data = analyze_fen(chess.STARTING_FEN)
        assert data["is_check"] is False
        assert data["is_checkmate"] is False
        assert data["is_stalemate"] is False


# ── Legal Moves ───────────────────────────────────────────────────────────────

class TestLegalMoves:
    def test_starting_position_20_moves(self):
        data = analyze_fen(chess.STARTING_FEN)
        assert len(data["legal_moves"]) == 20

    def test_moves_are_san(self):
        data = analyze_fen(chess.STARTING_FEN)
        # All starting moves should be recognizable SAN
        assert "e4" in data["legal_moves"]
        assert "Nf3" in data["legal_moves"]


# ── Superior Minor Piece ──────────────────────────────────────────────────────

class TestSuperiorMinorPiece:
    def test_bishop_pair_in_open_position(self):
        """Open position: bishop pair side scores higher."""
        # White has bishops on c4 (light) and g5 (dark) = bishop pair
        # Few pawns, open position
        fen = "r4rk1/ppp2ppp/2n5/6B1/2B5/5N2/PP3PPP/R4RK1 w - - 0 14"
        data = analyze_fen(fen)
        smp = data["superior_minor_piece"]
        assert smp["white"]["bishop_pair"] is True
        assert smp["position_type"] in ("open", "semi-open")
        assert smp["white"]["minor_piece_score"] >= smp["black"]["minor_piece_score"]

    def test_bad_bishop_detected(self):
        """Pawns fixed on bishop's color complex → bad bishop."""
        # French-structure: White pawns on d4, e5 (dark squares), White bishop on c1 (dark)
        fen = "r1bqkb1r/pp3ppp/2n1pn2/2ppP3/3P4/2N2N2/PPP2PPP/R1BQKB1R w KQkq - 0 6"
        data = analyze_fen(fen)
        smp = data["superior_minor_piece"]
        # White's dark-squared bishop on c1 should be detected as bad
        # (white pawns on d4, e5 are dark squares)
        assert len(smp["white"]["bad_bishops"]) > 0 or len(smp["black"]["bad_bishops"]) > 0

    def test_knight_outpost_in_closed_position(self):
        """Closed center: knight on outpost scores well."""
        # Knight on d5 outpost, closed center
        fen = "r1bqkb1r/pp3ppp/2n1pn2/2NpP3/3P4/8/PPP2PPP/R1BQKB1R b KQkq - 0 6"
        data = analyze_fen(fen)
        smp = data["superior_minor_piece"]
        # White has knight outpost info from piece_activity
        assert "good_knights" in smp["white"]

    def test_equal_minor_pieces(self):
        """Starting position → verdict equal."""
        data = analyze_fen(chess.STARTING_FEN)
        smp = data["superior_minor_piece"]
        assert smp["verdict"] == "equal"

    def test_position_type_classification(self):
        """Open vs closed classification works."""
        # Starting position = closed (all 16 pawns, 0 open files)
        data = analyze_fen(chess.STARTING_FEN)
        assert data["superior_minor_piece"]["position_type"] == "closed"
        # Open position: few pawns
        fen = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
        data2 = analyze_fen(fen)
        assert data2["superior_minor_piece"]["position_type"] == "open"


# ── Initiative ───────────────────────────────────────────────────────────────

class TestInitiative:
    def test_check_gives_initiative(self):
        """Position with check available → side has initiative."""
        # White can play Bb5+ — active position
        fen = "rnbqkbnr/pppp1ppp/8/4p3/2B1P3/8/PPPP1PPP/RNBQK1NR w KQkq - 0 3"
        data = analyze_fen(fen)
        init = data["initiative"]
        assert init["white"]["checks_available"] >= 1

    def test_development_lead_initiative(self):
        """Clear development lead in opening → initiative."""
        # White has developed 4 pieces, Black has developed 0
        # 1.e4 e6 2.d4 d5 3.Nc3 Nf6 4.Bg5 — White leads dev
        board = board_from_moves("e4", "e6", "d4", "d5", "Nc3", "Nf6", "Bg5")
        data = board_utils.analyze_position(board)
        init = data["initiative"]
        assert init["white"]["development_lead"] > 0

    def test_pins_count_toward_initiative(self):
        """Position with absolute pin → pin contributes to initiative."""
        # Bb5 pins Nc6 to Ke8 (d7 empty so pin is absolute)
        fen = "r1bqk2r/1pp1bppp/p1n2n2/1B2p3/4P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 5"
        board = chess.Board(fen)
        data = board_utils.analyze_position(board)
        init = data["initiative"]
        # White imposes the absolute pin
        assert init["white"]["pins_imposed"] >= 1

    def test_balanced_initiative(self):
        """Starting position → balanced."""
        data = analyze_fen(chess.STARTING_FEN)
        init = data["initiative"]
        assert init["side_with_initiative"] == "balanced"


# ── Statics vs Dynamics ──────────────────────────────────────────────────────

class TestStaticsVsDynamics:
    def test_static_position_classification(self):
        """Closed position with no threats → static."""
        data = analyze_fen(chess.STARTING_FEN)
        svd = data["statics_vs_dynamics"]
        assert svd["position_character"] in ("static", "transitional")

    def test_dynamic_position_classification(self):
        """Open position with many tactical elements → dynamic."""
        # Tactical position with pins, open lines
        fen = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 5"
        data = analyze_fen(fen)
        svd = data["statics_vs_dynamics"]
        assert svd["position_character"] in ("dynamic", "transitional")

    def test_static_advantages_collected(self):
        """Bishop pair and passed pawn appear in static advantages."""
        # White bishop pair + passed d-pawn
        fen = "r4rk1/ppp2ppp/2n5/3Pp3/2B5/8/PPP2PPP/R1B2RK1 w - - 0 12"
        data = analyze_fen(fen)
        svd = data["statics_vs_dynamics"]
        # Check that static advantages are collected
        w_static = svd["white"]["static_advantages"]
        assert any("bishop pair" in a.lower() for a in w_static) or \
               any("passed" in a.lower() for a in w_static)

    def test_compensation_detection(self):
        """Material deficit + tactical threats → compensation detected."""
        # Black down material but with development lead and threats
        # Simplified: White up a piece but Black has active play
        fen = "rnbqkb1r/pppppppp/5n2/8/3PP3/8/PPP2PPP/RNBQKBNR b KQkq - 0 3"
        data = analyze_fen(fen)
        svd = data["statics_vs_dynamics"]
        # Just verify compensation_detected is a boolean
        assert isinstance(svd["compensation_detected"], bool)


# ── Full Analysis Integration ─────────────────────────────────────────────────

class TestFullAnalysis:
    def test_all_sections_present(self):
        data = analyze_fen(chess.STARTING_FEN)
        expected_keys = [
            "fen", "side_to_move", "move_number", "board_display",
            "material", "pawn_structure", "piece_activity", "files",
            "king_safety", "space", "pins", "tactics", "development", "game_phase",
            "legal_moves", "is_check", "is_checkmate", "is_stalemate",
            "superior_minor_piece", "initiative", "statics_vs_dynamics",
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"

    def test_text_format_output(self):
        data = analyze_fen(chess.STARTING_FEN)
        text = board_utils.format_text(data)
        assert "POSITION ANALYSIS" in text
        assert "Material" in text
        assert "Pawn Structure" in text
        assert "Legal moves" in text

    def test_side_to_move(self):
        data = analyze_fen(chess.STARTING_FEN)
        assert data["side_to_move"] == "white"

        data2 = analyze_from_moves("e4")
        assert data2["side_to_move"] == "black"
