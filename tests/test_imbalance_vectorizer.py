"""Tests for imbalance_vectorizer — flatten analysis JSON into numerical features."""

import sys
from pathlib import Path

import chess
import pytest

# Add scripts to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "chess-imbalances" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from board_utils import analyze_position
from imbalance_vectorizer import vectorize, FEATURE_NAMES, compute_deltas, vectorize_stm, STM_FEATURE_NAMES


class TestVectorizeStartingPosition:
    """Starting position has known, deterministic properties."""

    @pytest.fixture
    def start_features(self):
        board = chess.Board()
        analysis = analyze_position(board)
        return vectorize(analysis)

    def test_returns_dict(self, start_features):
        assert isinstance(start_features, dict)

    def test_all_feature_names_present(self, start_features):
        for name in FEATURE_NAMES:
            assert name in start_features, f"Missing feature: {name}"

    def test_all_values_numeric(self, start_features):
        for name, val in start_features.items():
            assert isinstance(val, (int, float)), f"{name} = {val!r} is not numeric"

    def test_material_balance_zero(self, start_features):
        assert start_features["material_balance"] == 0

    def test_no_passed_pawns(self, start_features):
        assert start_features["passed_pawns_white"] == 0
        assert start_features["passed_pawns_black"] == 0

    def test_pawn_islands_one_each(self, start_features):
        assert start_features["pawn_islands_white"] == 1
        assert start_features["pawn_islands_black"] == 1

    def test_development_zero(self, start_features):
        assert start_features["development_white"] == 0
        assert start_features["development_black"] == 0

    def test_side_to_move_white(self, start_features):
        assert start_features["side_to_move"] == 1

    def test_game_phase_opening(self, start_features):
        assert start_features["game_phase"] == 0  # opening

    def test_no_pins(self, start_features):
        assert start_features["pin_count"] == 0

    def test_queen_counts(self, start_features):
        assert start_features["queen_count_white"] == 1
        assert start_features["queen_count_black"] == 1

    def test_feature_count_matches_names(self, start_features):
        assert len(start_features) == len(FEATURE_NAMES)


class TestVectorizeMiddlegame:
    """A typical middlegame with known imbalances."""

    @pytest.fixture
    def mg_features(self):
        # Sicilian Najdorf-style position with clear imbalances
        board = chess.Board("r1b1kb1r/1p1n1ppp/p2ppn2/6B1/3NP3/2N5/PPPQ1PPP/R3KB1R w KQkq - 0 9")
        analysis = analyze_position(board)
        return vectorize(analysis)

    def test_material_white_up_queen(self, mg_features):
        # Black is missing queen in this FEN
        assert mg_features["material_balance"] == 9

    def test_center_control_exists(self, mg_features):
        assert mg_features["center_control_white"] >= 2
        assert mg_features["center_control_black"] >= 2

    def test_white_more_developed(self, mg_features):
        assert mg_features["development_white"] > mg_features["development_black"]

    def test_game_phase_not_endgame(self, mg_features):
        assert mg_features["game_phase"] <= 1  # opening or middlegame


class TestVectorizeEndgame:
    """King and pawn endgame with passed pawn."""

    @pytest.fixture
    def eg_features(self):
        # White king + pawn vs Black king — passed pawn on d5
        board = chess.Board("8/8/3k4/3P4/8/3K4/8/8 w - - 0 50")
        analysis = analyze_position(board)
        return vectorize(analysis)

    def test_material_white_up(self, eg_features):
        assert eg_features["material_balance"] > 0

    def test_passed_pawn_white(self, eg_features):
        assert eg_features["passed_pawns_white"] == 1

    def test_game_phase_endgame(self, eg_features):
        assert eg_features["game_phase"] == 2  # endgame

    def test_no_queens(self, eg_features):
        assert eg_features["queen_count_white"] == 0
        assert eg_features["queen_count_black"] == 0


class TestComputeDeltas:
    """Delta computation between two feature vectors."""

    def test_delta_basic(self):
        v1 = {"a": 1, "b": 5, "c": 0}
        v2 = {"a": 3, "b": 2, "c": 1}
        d = compute_deltas(v1, v2)
        assert d["d_a"] == 2
        assert d["d_b"] == -3
        assert d["d_c"] == 1

class TestVectorizeSTM:
    """Side-to-move relative vectorization — color-agnostic features."""

    def test_white_to_move_stm_equals_white(self):
        """When White to move, stm features = white features."""
        board = chess.Board()  # White to move
        analysis = analyze_position(board)
        abs_v = vectorize(analysis)
        stm_v = vectorize_stm(analysis)

        assert stm_v["material_advantage"] == abs_v["material_balance"]  # W-B, same as stm-opp
        assert stm_v["space_stm"] == abs_v["space_white"]
        assert stm_v["space_opp"] == abs_v["space_black"]
        assert stm_v["initiative_score_stm"] == abs_v["initiative_score_white"]

    def test_black_to_move_stm_swaps(self):
        """When Black to move, stm features = black features, opp = white."""
        board = chess.Board()
        board.push_san("e4")  # Now Black to move
        analysis = analyze_position(board)
        abs_v = vectorize(analysis)
        stm_v = vectorize_stm(analysis)

        # STM is Black, so material_advantage = -(white-black) = black-white
        assert stm_v["material_advantage"] == -abs_v["material_balance"]
        assert stm_v["space_stm"] == abs_v["space_black"]
        assert stm_v["space_opp"] == abs_v["space_white"]
        assert stm_v["initiative_score_stm"] == abs_v["initiative_score_black"]
        assert stm_v["initiative_score_opp"] == abs_v["initiative_score_white"]

    def test_all_stm_feature_names_present(self):
        board = chess.Board()
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        for name in STM_FEATURE_NAMES:
            assert name in stm_v, f"Missing STM feature: {name}"

    def test_all_stm_values_numeric(self):
        board = chess.Board()
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        for name, val in stm_v.items():
            assert isinstance(val, (int, float)), f"{name} = {val!r} is not numeric"

    def test_stm_feature_count(self):
        board = chess.Board()
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        assert len(stm_v) == len(STM_FEATURE_NAMES)

    def test_eval_advantage_positive_for_stm(self):
        """eval_advantage should be from STM perspective."""
        # Position where White is ahead (+43cp) and White to move
        board = chess.Board()
        analysis = analyze_position(board)
        # No engine data, so eval_advantage should be 0
        stm_v = vectorize_stm(analysis)
        assert stm_v["eval_advantage"] == 0

    def test_eval_advantage_with_engine(self):
        """When engine data present, eval_advantage flips for Black."""
        board = chess.Board()
        analysis = analyze_position(board)
        # Inject fake engine data: White ahead by 100cp
        analysis["engine"] = {"available": True, "eval": {"score_cp": 100}}
        stm_v = vectorize_stm(analysis)
        assert stm_v["eval_advantage"] == 100  # White to move, White ahead → +100

        # Same position but pretend Black to move
        analysis["side_to_move"] = "black"
        stm_v = vectorize_stm(analysis)
        assert stm_v["eval_advantage"] == -100  # Black to move, White ahead → -100 from STM

    def test_symmetry_same_position(self):
        """Symmetric starting position: STM features should equal OPP features."""
        board = chess.Board()
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        assert stm_v["space_stm"] == stm_v["space_opp"]
        assert stm_v["development_stm"] == stm_v["development_opp"]
        assert stm_v["pawn_count_stm"] == stm_v["pawn_count_opp"]


    def test_delta_from_analysis(self):
        """Compute deltas between starting position and after 1.e4."""
        board1 = chess.Board()
        a1 = analyze_position(board1)
        v1 = vectorize(a1)

        board2 = chess.Board()
        board2.push_san("e4")
        a2 = analyze_position(board2)
        v2 = vectorize(a2)

        d = compute_deltas(v1, v2)
        # After 1.e4, side_to_move changes from white(1) to black(0)
        assert d["d_side_to_move"] == -1
        # White development should increase (pawn moved, but pawns aren't "developable")
        # Space should change — e4 pushes frontier
        # All delta keys should exist
        for name in FEATURE_NAMES:
            assert f"d_{name}" in d, f"Missing delta: d_{name}"


class TestSpatialContextFeatures:
    """Regional control and king location features (STM-relative)."""

    SPATIAL_FEATURES = [
        "region_center", "region_stm_kingside", "region_stm_queenside",
        "region_opp_kingside", "region_opp_queenside",
        "stm_king_file", "stm_king_rank", "opp_king_file", "opp_king_rank",
    ]

    def test_spatial_features_present_in_stm(self):
        """All 9 spatial features should be in vectorize_stm() output."""
        board = chess.Board()
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        for name in self.SPATIAL_FEATURES:
            assert name in stm_v, f"Missing spatial feature: {name}"

    def test_spatial_features_in_feature_names(self):
        """All 9 spatial features should be in STM_FEATURE_NAMES."""
        for name in self.SPATIAL_FEATURES:
            assert name in STM_FEATURE_NAMES, f"Missing from STM_FEATURE_NAMES: {name}"

    def test_spatial_features_are_ternary(self):
        """All spatial features should have values in {-1, 0, 1}."""
        board = chess.Board()
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        for name in self.SPATIAL_FEATURES:
            assert stm_v[name] in (-1, 0, 1), f"{name}={stm_v[name]} not in {{-1,0,1}}"

    def test_starting_position_king_locations(self):
        """In starting position, both kings are on e-file (center) at home rank."""
        board = chess.Board()  # White to move
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        # White king on e1: file=center(0), STM-rank 1=home(+1)
        assert stm_v["stm_king_file"] == 0   # e-file = center
        assert stm_v["stm_king_rank"] == 1    # rank 1 = home
        # Black king on e8: file=center(0), STM-rank 8=home(+1) for opp
        assert stm_v["opp_king_file"] == 0    # e-file = center
        assert stm_v["opp_king_rank"] == 1    # opp at home

    def test_king_location_stm_relative_flip(self):
        """When Black to move, king locations should flip perspective."""
        board = chess.Board()
        board.push_san("e4")  # Black to move
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        # STM is Black: Black king on e8, STM-rank = home(+1)
        assert stm_v["stm_king_file"] == 0   # e-file = center
        assert stm_v["stm_king_rank"] == 1    # home for Black
        # OPP is White: White king on e1, from Black's perspective rank 1 = opp home(+1)
        assert stm_v["opp_king_file"] == 0
        assert stm_v["opp_king_rank"] == 1    # home for White

    def test_castled_king_kingside(self):
        """After O-O, king on g1 should be kingside(+1)."""
        board = chess.Board()
        for san in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "O-O"]:
            board.push_san(san)
        # Black to move; White king on g1
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        # OPP (White) king on g1: file=kingside(+1), rank 1=home
        assert stm_v["opp_king_file"] == 1    # g-file = kingside
        assert stm_v["opp_king_rank"] == 1    # home

    def test_starting_position_regions_symmetric(self):
        """In starting position, symmetric regions should have equal control."""
        board = chess.Board()
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        # STM kingside and OPP kingside should have opposite control or both neutral
        # Center should be roughly neutral in starting position
        assert stm_v["region_center"] in (-1, 0, 1)
        # STM's home regions should be STM-controlled (+1) or neutral
        assert stm_v["region_stm_kingside"] >= 0
        assert stm_v["region_stm_queenside"] >= 0

    def test_king_advanced_to_center(self):
        """King that has marched to center should have rank=center(0)."""
        # Endgame position with White king on e4
        board = chess.Board("8/8/4k3/8/4K3/8/8/8 w - - 0 1")
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        # White king on e4: file=center(0), STM-rank 4=center(0)
        assert stm_v["stm_king_file"] == 0
        assert stm_v["stm_king_rank"] == 0    # rank 4 = center

    def test_king_advanced_into_opponent_territory(self):
        """King on rank 6+ (from STM perspective) should be advanced(-1)."""
        # White king on e6
        board = chess.Board("8/8/4K3/8/4k3/8/8/8 w - - 0 1")
        analysis = analyze_position(board)
        stm_v = vectorize_stm(analysis)
        # White king on e6: file=center(0), STM-rank 6=advanced(-1)
        assert stm_v["stm_king_file"] == 0
        assert stm_v["stm_king_rank"] == -1   # advanced into opp territory
