"""Tests for MRE (Most Relevant Explanation) inference on chess BN.

TDD: test structure written before implementation.
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / ".claude" / "skills" / "chess-imbalances" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

ANALYSIS_DIR = Path(__file__).parent.parent / "analysis"
BIF_PATH = ANALYSIS_DIR / "chess_bn.bif"


@pytest.fixture
def mre_engine():
    """Load the chess BN and create an MRE engine."""
    pytest.importorskip("pgmpy")
    from mre_inference import MREEngine
    return MREEngine.from_bif(str(BIF_PATH))


class TestGBFComputation:
    """Generalized Bayes Factor computation."""

    @pytest.mark.skipif(not BIF_PATH.exists(), reason="BN model not available")
    def test_gbf_positive_for_material_gain(self, mre_engine):
        """Material gain should have GBF > 1 for improvement."""
        gbf = mre_engine.compute_gbf(
            explanation={"d_material_advantage": "pos"},
            evidence={"eval_change": "improvement"},
        )
        assert gbf > 1.0

    @pytest.mark.skipif(not BIF_PATH.exists(), reason="BN model not available")
    def test_gbf_less_than_one_for_contradictory(self, mre_engine):
        """Material gain should have GBF < 1 for decline."""
        gbf = mre_engine.compute_gbf(
            explanation={"d_material_advantage": "pos"},
            evidence={"eval_change": "decline"},
        )
        assert gbf < 1.0

    @pytest.mark.skipif(not BIF_PATH.exists(), reason="BN model not available")
    def test_gbf_compound_reflects_explaining_away(self, mre_engine):
        """Adding a variable to an explanation can decrease GBF (explaining away).

        When material gain already explains the eval improvement, adding initiative
        may not help — the GBF can stay flat or decrease. This is correct MRE behavior:
        only variables that genuinely improve explanatory power increase GBF.
        """
        gbf_single = mre_engine.compute_gbf(
            explanation={"d_material_advantage": "pos"},
            evidence={"eval_change": "improvement"},
        )
        gbf_compound = mre_engine.compute_gbf(
            explanation={"d_material_advantage": "pos", "d_initiative_score_stm": "pos"},
            evidence={"eval_change": "improvement"},
        )
        # Both should be > 1 (both are relevant explanations)
        assert gbf_single > 1.0
        assert gbf_compound > 1.0
        # GBF may increase OR decrease — explaining away is valid
        # The key property: compound GBF is still reasonable (not collapsed)
        assert gbf_compound > 0.5 * gbf_single  # shouldn't collapse dramatically

    @pytest.mark.skipif(not BIF_PATH.exists(), reason="BN model not available")
    def test_gbf_symmetric_material(self, mre_engine):
        """Material loss explaining decline should have similar GBF to material gain explaining improvement."""
        gbf_gain = mre_engine.compute_gbf(
            explanation={"d_material_advantage": "pos"},
            evidence={"eval_change": "improvement"},
        )
        gbf_loss = mre_engine.compute_gbf(
            explanation={"d_material_advantage": "neg"},
            evidence={"eval_change": "decline"},
        )
        assert abs(gbf_gain - gbf_loss) / max(gbf_gain, gbf_loss) < 0.3  # within 30%


class TestMRESearch:
    """MRE beam search for most relevant explanations."""

    @pytest.mark.skipif(not BIF_PATH.exists(), reason="BN model not available")
    def test_mre_returns_explanation(self, mre_engine):
        """MRE should return at least one explanation."""
        result = mre_engine.find_mre(
            evidence={"eval_change": "improvement"},
            beam_width=5,
        )
        assert len(result) > 0

    @pytest.mark.skipif(not BIF_PATH.exists(), reason="BN model not available")
    def test_mre_explanation_has_gbf(self, mre_engine):
        """Each MRE result should have a GBF score."""
        results = mre_engine.find_mre(
            evidence={"eval_change": "improvement"},
            beam_width=5,
        )
        for explanation, gbf in results:
            assert isinstance(gbf, float)
            assert gbf > 0

    @pytest.mark.skipif(not BIF_PATH.exists(), reason="BN model not available")
    def test_mre_explanation_is_partial(self, mre_engine):
        """MRE should return partial instantiations, not all variables."""
        results = mre_engine.find_mre(
            evidence={"eval_change": "improvement"},
            beam_width=5,
        )
        best_explanation, _ = results[0]
        # Should have fewer variables than total target variables
        total_targets = len(mre_engine.target_variables)
        assert len(best_explanation) < total_targets

    @pytest.mark.skipif(not BIF_PATH.exists(), reason="BN model not available")
    def test_mre_sorted_by_gbf(self, mre_engine):
        """Results should be sorted by GBF descending."""
        results = mre_engine.find_mre(
            evidence={"eval_change": "improvement"},
            beam_width=5,
        )
        gbfs = [gbf for _, gbf in results]
        assert gbfs == sorted(gbfs, reverse=True)

    @pytest.mark.skipif(not BIF_PATH.exists(), reason="BN model not available")
    def test_mre_for_decline(self, mre_engine):
        """MRE for decline should mention material loss or similar."""
        results = mre_engine.find_mre(
            evidence={"eval_change": "decline"},
            beam_width=5,
        )
        assert len(results) > 0
        best_explanation, gbf = results[0]
        assert gbf > 1.0  # should find at least one relevant explanation

    @pytest.mark.skipif(not BIF_PATH.exists(), reason="BN model not available")
    def test_mre_top_k(self, mre_engine):
        """Should be able to request top-k diverse explanations."""
        results = mre_engine.find_mre(
            evidence={"eval_change": "improvement"},
            beam_width=10,
            top_k=3,
        )
        assert len(results) <= 3


class TestMREOutput:
    """MRE output formatting."""

    @pytest.mark.skipif(not BIF_PATH.exists(), reason="BN model not available")
    def test_format_explanation(self, mre_engine):
        """Explanation should format as human-readable string."""
        from mre_inference import format_mre_explanation
        results = mre_engine.find_mre(
            evidence={"eval_change": "improvement"},
            beam_width=5,
        )
        text = format_mre_explanation(results[0])
        assert isinstance(text, str)
        assert len(text) > 0
