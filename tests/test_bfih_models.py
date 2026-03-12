"""Tests for BFIH phase models — TDD Red phase.

Tests all 9 BFIH phases plus the composite BFIHAnalysis model.
Validates Pydantic constraints, custom validators, and enum usage.
"""

import pytest
from pydantic import ValidationError

import sys
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "chess-imbalances" / "scripts"))

from bfih_models import (
    Paradigm, Confidence, Relevance, Direction, Likelihood, Assessment,
    K0, Hypothesis, HypothesisSet, ImbalanceFinding, OntologicalScan,
    AncestralCheck, ParadigmInversion, EvidenceRow, PosteriorUpdate,
    EvidenceMatrix, ReflexiveReview, Synthesis, CandidateMove,
    DiscomfortHeuristic, BFIHAnalysis,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_k0(**overrides):
    defaults = {
        "opening_context": "Sicilian Najdorf, a sharp and theoretical opening",
        "paradigm": "dynamic",
        "gut_read": "White has a slight edge due to central control and development lead",
        "gut_read_assessment": "white_slight",
        "confidence": "moderate",
        "disconfirming_triggers": [
            "Black's counterplay on the c-file proves sufficient",
            "White's central pawns become targets rather than strengths",
        ],
    }
    defaults.update(overrides)
    return K0(**defaults)


def make_hypothesis_set(**overrides):
    defaults = {
        "hypotheses": [
            {"id": "H1", "prior": 0.45, "assessment": "white_slight",
             "description": "White is slightly better due to space and center",
             "plan": "Expand on the kingside while maintaining center"},
            {"id": "H2", "prior": 0.30, "assessment": "equal",
             "description": "Position is dynamically balanced with mutual chances",
             "plan": "Both sides have counterplay"},
            {"id": "H3", "prior": 0.15, "assessment": "black_slight",
             "description": "Black's piece activity compensates for structural issues",
             "plan": "Black plays for active pieces"},
            {"id": "H_catch", "prior": 0.10, "assessment": "equal",
             "description": "Position is more complex than the above captures",
             "plan": "Deeper analysis needed"},
        ]
    }
    defaults.update(overrides)
    return HypothesisSet(**defaults)


def make_ontological_scan(**overrides):
    names = [
        "Superior Minor Piece", "Pawn Structure", "Space", "Material",
        "Control of Key File", "Control of Hole / Weak Square",
        "Lead in Development", "Initiative", "King Safety",
        "Statics vs Dynamics",
    ]
    defaults = {
        "findings": [
            {
                "number": i,
                "name": names[i - 1],
                "finding": f"Finding for imbalance {i} with enough detail",
                "relevance": "moderate",
                "direction": "neutral",
                "interaction": f"Interacts with other imbalances",
            }
            for i in range(1, 11)
        ]
    }
    defaults.update(overrides)
    return OntologicalScan(**defaults)


def make_ancestral_check(**overrides):
    defaults = {
        "structural_analogy": "Resembles a typical Carlsbad structure with minority attack themes",
        "paradigm_precedent": "Karpov would squeeze; Kasparov would seek initiative on the kingside",
        "engine_vs_human": "Engine may overvalue White's space; humans would note Black's solid structure",
        "historical_pitfalls": "White often overextends trying to exploit space advantage",
    }
    defaults.update(overrides)
    return AncestralCheck(**defaults)


def make_paradigm_inversion(**overrides):
    defaults = {
        "inverted_argument": (
            "Black actually has the better position because the pawn structure "
            "gives long-term targets on the queenside, and White's space advantage "
            "is illusory since the pawns can become overextended."
        ),
        "inverted_assessment": "black_slight",
        "new_considerations": [
            "White's d4 pawn may become a target in the endgame",
        ],
        "felt_easy_to_dismiss": False,
        "probability_shift": -0.10,
    }
    defaults.update(overrides)
    return ParadigmInversion(**defaults)


def make_evidence_matrix(**overrides):
    defaults = {
        "rows": [
            {"finding": "White has bishop pair advantage",
             "ratings": {"H1": "++", "H2": "+", "H3": "0", "H_catch": "0"}},
            {"finding": "Black knight on d5 is very strong",
             "ratings": {"H1": "-", "H2": "++", "H3": "++", "H_catch": "0"}},
            {"finding": "Open e-file favors White's rooks",
             "ratings": {"H1": "++", "H2": "+", "H3": "-", "H_catch": "0"}},
        ],
        "posteriors": [
            {"hypothesis_id": "H1", "prior": 0.45, "posterior": 0.40,
             "reasoning": "Bishop pair advantage offset by Black's strong knight"},
            {"hypothesis_id": "H2", "prior": 0.30, "posterior": 0.30,
             "reasoning": "Evidence roughly balanced for this hypothesis"},
            {"hypothesis_id": "H3", "prior": 0.15, "posterior": 0.20,
             "reasoning": "Black's knight outpost stronger than initially assessed"},
            {"hypothesis_id": "H_catch", "prior": 0.10, "posterior": 0.10,
             "reasoning": "No surprising evidence to increase catch-all"},
        ],
    }
    defaults.update(overrides)
    return EvidenceMatrix(**defaults)


def make_reflexive_review(**overrides):
    defaults = {
        "k0_comparison": "Initial gut read of White slight advantage mostly confirmed but tempered",
        "most_surprising_finding": "Black's knight on d5 is much stronger than initially assessed",
        "paradigm_sensitivity": "Positional analyst would favor White; dynamic analyst would call it equal",
        "red_team_argument": (
            "The entire White advantage is based on static factors "
            "that may not matter if Black generates concrete threats"
        ),
        "genuine_update": True,
    }
    defaults.update(overrides)
    return ReflexiveReview(**defaults)


def make_synthesis(**overrides):
    defaults = {
        "assessment": "white_slight",
        "confidence": "moderate",
        "key_imbalances": ["Superior Minor Piece", "Pawn Structure"],
        "paradigm_note": "Assessment is paradigm-dependent; dynamic view sees equal",
        "k0_revision": "Initial read was slightly too optimistic for White",
        "disconfirming_evidence": ["Black's strong knight outpost on d5"],
        "candidate_moves": [
            {"move": "Bf4", "rationale": "Activates bishop and eyes the e5 outpost"},
            {"move": "Nd2", "rationale": "Rerouting knight to better square"},
            {"move": "Re1", "rationale": "Controls the open e-file"},
        ],
    }
    defaults.update(overrides)
    return Synthesis(**defaults)


def make_discomfort_heuristic(**overrides):
    defaults = {
        "feels_comfortable": False,
        "confidence_drop_moment": "When analyzing Black's knight outpost potential",
        "more_uncertain_than_start": True,
        "warning": None,
    }
    defaults.update(overrides)
    return DiscomfortHeuristic(**defaults)


# ── TestK0 ───────────────────────────────────────────────────────────────────

class TestK0:
    def test_valid(self):
        k0 = make_k0()
        assert k0.paradigm == Paradigm.dynamic
        assert k0.confidence == Confidence.moderate
        assert len(k0.disconfirming_triggers) == 2

    def test_opening_context_too_short(self):
        with pytest.raises(ValidationError, match="opening_context"):
            make_k0(opening_context="Short")

    def test_gut_read_too_short(self):
        with pytest.raises(ValidationError, match="gut_read"):
            make_k0(gut_read="White is better")

    def test_triggers_too_few(self):
        with pytest.raises(ValidationError, match="disconfirming_triggers"):
            make_k0(disconfirming_triggers=["Only one trigger here"])

    def test_triggers_too_many(self):
        with pytest.raises(ValidationError, match="disconfirming_triggers"):
            make_k0(disconfirming_triggers=[
                "Trigger one is here", "Trigger two is here",
                "Trigger three here", "Trigger four here",
                "Trigger five here",
            ])

    def test_trigger_too_short(self):
        with pytest.raises(ValidationError, match="15 characters"):
            make_k0(disconfirming_triggers=["Too short", "Also too short"])


# ── TestHypothesisSet ────────────────────────────────────────────────────────

class TestHypothesisSet:
    def test_valid(self):
        hs = make_hypothesis_set()
        assert len(hs.hypotheses) == 4
        assert sum(h.prior for h in hs.hypotheses) == pytest.approx(1.0, abs=0.01)

    def test_priors_sum_to_one(self):
        """Priors summing to exactly 1.0 should pass."""
        hs = make_hypothesis_set()
        assert sum(h.prior for h in hs.hypotheses) == pytest.approx(1.0, abs=0.01)

    def test_priors_dont_sum(self):
        with pytest.raises(ValidationError, match="sum to 1.0"):
            make_hypothesis_set(hypotheses=[
                {"id": "H1", "prior": 0.50, "assessment": "white_slight",
                 "description": "White is slightly better due to space",
                 "plan": "Expand on kingside"},
                {"id": "H_catch", "prior": 0.20, "assessment": "equal",
                 "description": "Position is more complex than captured",
                 "plan": "Deeper analysis needed"},
            ])

    def test_too_few_hypotheses(self):
        with pytest.raises(ValidationError, match="hypotheses"):
            make_hypothesis_set(hypotheses=[
                {"id": "H1", "prior": 0.90, "assessment": "white_slight",
                 "description": "White is slightly better due to space",
                 "plan": "Expand on kingside"},
            ])

    def test_too_many_hypotheses(self):
        with pytest.raises(ValidationError, match="hypotheses"):
            make_hypothesis_set(hypotheses=[
                {"id": f"H{i}", "prior": 1/7, "assessment": "equal",
                 "description": f"Hypothesis {i} with enough description text",
                 "plan": "Some plan here"}
                for i in range(1, 7)
            ] + [
                {"id": "H_catch", "prior": 1/7, "assessment": "equal",
                 "description": "Catch-all hypothesis description text",
                 "plan": "Deeper analysis"},
            ])

    def test_duplicate_ids(self):
        with pytest.raises(ValidationError, match="unique"):
            make_hypothesis_set(hypotheses=[
                {"id": "H1", "prior": 0.40, "assessment": "white_slight",
                 "description": "White is slightly better due to space",
                 "plan": "Expand on kingside"},
                {"id": "H1", "prior": 0.30, "assessment": "equal",
                 "description": "Position is dynamically balanced overall",
                 "plan": "Both sides play"},
                {"id": "H_catch", "prior": 0.30, "assessment": "equal",
                 "description": "Position is more complex than captured",
                 "plan": "Deeper analysis needed"},
            ])

    def test_missing_h_catch(self):
        with pytest.raises(ValidationError, match="H_catch"):
            make_hypothesis_set(hypotheses=[
                {"id": "H1", "prior": 0.50, "assessment": "white_slight",
                 "description": "White is slightly better due to space",
                 "plan": "Expand on kingside"},
                {"id": "H2", "prior": 0.50, "assessment": "equal",
                 "description": "Position is dynamically balanced overall",
                 "plan": "Both sides play"},
            ])

    def test_h_catch_required(self):
        """H_catch must be present even if other hypotheses are valid."""
        with pytest.raises(ValidationError, match="H_catch"):
            make_hypothesis_set(hypotheses=[
                {"id": "H1", "prior": 0.45, "assessment": "white_slight",
                 "description": "White is slightly better due to space",
                 "plan": "Expand on kingside"},
                {"id": "H2", "prior": 0.30, "assessment": "equal",
                 "description": "Position is dynamically balanced overall",
                 "plan": "Both sides play"},
                {"id": "H3", "prior": 0.25, "assessment": "black_slight",
                 "description": "Black's piece activity compensates fully",
                 "plan": "Black plays for active pieces"},
            ])


# ── TestOntologicalScan ──────────────────────────────────────────────────────

class TestOntologicalScan:
    def test_valid_10(self):
        scan = make_ontological_scan()
        assert len(scan.findings) == 10

    def test_fewer_than_10(self):
        with pytest.raises(ValidationError, match="10"):
            OntologicalScan(findings=[
                {"number": i, "name": f"Imbalance {i}",
                 "finding": f"Finding for imbalance {i} detail",
                 "relevance": "moderate", "direction": "neutral",
                 "interaction": "Some interaction"}
                for i in range(1, 9)
            ])

    def test_more_than_10(self):
        with pytest.raises(ValidationError, match="10"):
            OntologicalScan(findings=[
                {"number": i, "name": f"Imbalance {i}",
                 "finding": f"Finding for imbalance {i} detail",
                 "relevance": "moderate", "direction": "neutral",
                 "interaction": "Some interaction"}
                for i in range(1, 13)
            ])

    def test_duplicate_numbers(self):
        with pytest.raises(ValidationError, match="unique"):
            findings = [
                {"number": i, "name": f"Imbalance {i}",
                 "finding": f"Finding for imbalance {i} detail",
                 "relevance": "moderate", "direction": "neutral",
                 "interaction": "Some interaction"}
                for i in range(1, 10)
            ]
            # Add duplicate number 1 instead of number 10
            findings.append(
                {"number": 1, "name": "Duplicate",
                 "finding": "Duplicate finding with detail",
                 "relevance": "moderate", "direction": "neutral",
                 "interaction": "Some interaction"}
            )
            OntologicalScan(findings=findings)

    def test_missing_number(self):
        """Numbers 1-10 must all be present (e.g., missing 10, duplicate 9)."""
        with pytest.raises(ValidationError, match="1 through 10|unique"):
            findings = [
                {"number": i, "name": f"Imbalance {i}",
                 "finding": f"Finding for imbalance {i} detail",
                 "relevance": "moderate", "direction": "neutral",
                 "interaction": "Some interaction"}
                for i in range(1, 10)  # Missing 10
            ]
            # Duplicate 9 to get 10 items but miss number 10
            findings.append(
                {"number": 9, "name": "Duplicate Nine",
                 "finding": "Duplicate finding with detail",
                 "relevance": "moderate", "direction": "neutral",
                 "interaction": "Some interaction"}
            )
            OntologicalScan(findings=findings)


# ── TestImbalanceFinding ─────────────────────────────────────────────────────

class TestImbalanceFinding:
    def test_valid(self):
        f = ImbalanceFinding(
            number=1, name="Superior Minor Piece",
            finding="White's bishop pair is strong in this open position",
            relevance="high", direction="white", interaction="Pairs with space advantage",
        )
        assert f.number == 1
        assert f.relevance == Relevance.high

    def test_finding_too_short(self):
        with pytest.raises(ValidationError, match="finding"):
            ImbalanceFinding(
                number=1, name="Superior Minor Piece",
                finding="Short",
                relevance="high", direction="white", interaction="Some",
            )

    def test_number_out_of_range(self):
        with pytest.raises(ValidationError, match="number"):
            ImbalanceFinding(
                number=0, name="Invalid",
                finding="Finding text with enough detail",
                relevance="high", direction="white", interaction="Some",
            )


# ── TestAncestralCheck ───────────────────────────────────────────────────────

class TestAncestralCheck:
    def test_valid(self):
        ac = make_ancestral_check()
        assert "Carlsbad" in ac.structural_analogy

    def test_analogy_too_short(self):
        with pytest.raises(ValidationError, match="structural_analogy"):
            make_ancestral_check(structural_analogy="Too short")

    def test_precedent_too_short(self):
        with pytest.raises(ValidationError, match="paradigm_precedent"):
            make_ancestral_check(paradigm_precedent="Too short")


# ── TestParadigmInversion ────────────────────────────────────────────────────

class TestParadigmInversion:
    def test_valid(self):
        pi = make_paradigm_inversion()
        assert pi.inverted_assessment == Assessment.black_slight
        assert pi.felt_easy_to_dismiss is False

    def test_argument_too_short(self):
        with pytest.raises(ValidationError, match="inverted_argument"):
            make_paradigm_inversion(inverted_argument="Too short to be a real inversion")

    def test_quality_gate_fails(self):
        """felt_easy_to_dismiss=True AND abs(probability_shift) < 0.05 → reject."""
        with pytest.raises(ValidationError, match="quality gate"):
            make_paradigm_inversion(
                felt_easy_to_dismiss=True,
                probability_shift=0.02,
            )

    def test_quality_gate_passes_with_shift(self):
        """felt_easy_to_dismiss=True but sufficient shift → OK."""
        pi = make_paradigm_inversion(
            felt_easy_to_dismiss=True,
            probability_shift=-0.10,
        )
        assert pi.felt_easy_to_dismiss is True


# ── TestEvidenceMatrix ───────────────────────────────────────────────────────

class TestEvidenceMatrix:
    def test_valid(self):
        em = make_evidence_matrix()
        assert len(em.rows) == 3
        assert len(em.posteriors) == 4

    def test_too_few_rows(self):
        with pytest.raises(ValidationError, match="rows"):
            make_evidence_matrix(rows=[
                {"finding": "Only one finding here",
                 "ratings": {"H1": "++", "H2": "+"}},
                {"finding": "Only two findings total",
                 "ratings": {"H1": "+", "H2": "++"}},
            ])

    def test_posteriors_sum(self):
        em = make_evidence_matrix()
        total = sum(p.posterior for p in em.posteriors)
        assert total == pytest.approx(1.0, abs=0.01)

    def test_posteriors_dont_sum(self):
        with pytest.raises(ValidationError, match="sum to 1.0"):
            make_evidence_matrix(posteriors=[
                {"hypothesis_id": "H1", "prior": 0.45, "posterior": 0.50,
                 "reasoning": "Increased due to strong evidence support"},
                {"hypothesis_id": "H2", "prior": 0.30, "posterior": 0.30,
                 "reasoning": "Roughly unchanged by evidence review"},
                {"hypothesis_id": "H3", "prior": 0.15, "posterior": 0.30,
                 "reasoning": "Increased but now they don't sum"},
                {"hypothesis_id": "H_catch", "prior": 0.10, "posterior": 0.10,
                 "reasoning": "Unchanged catch-all probability"},
            ])

    def test_must_have_reasoning(self):
        with pytest.raises(ValidationError, match="reasoning"):
            make_evidence_matrix(posteriors=[
                {"hypothesis_id": "H1", "prior": 0.45, "posterior": 0.40,
                 "reasoning": "Short"},
                {"hypothesis_id": "H2", "prior": 0.30, "posterior": 0.30,
                 "reasoning": "Evidence roughly balanced for hypothesis"},
                {"hypothesis_id": "H3", "prior": 0.15, "posterior": 0.20,
                 "reasoning": "Knight outpost stronger than assessed"},
                {"hypothesis_id": "H_catch", "prior": 0.10, "posterior": 0.10,
                 "reasoning": "No surprising evidence to increase"},
            ])


# ── TestReflexiveReview ──────────────────────────────────────────────────────

class TestReflexiveReview:
    def test_valid(self):
        rr = make_reflexive_review()
        assert rr.genuine_update is True

    def test_red_team_too_short(self):
        with pytest.raises(ValidationError, match="red_team_argument"):
            make_reflexive_review(red_team_argument="Too short")


# ── TestSynthesis ────────────────────────────────────────────────────────────

class TestSynthesis:
    def test_valid(self):
        s = make_synthesis()
        assert s.assessment == Assessment.white_slight
        assert len(s.candidate_moves) == 3

    def test_candidate_move_with_engine_score(self):
        s = make_synthesis(candidate_moves=[
            {"move": "Bf4", "rationale": "Activates bishop and eyes the e5 outpost",
             "engine_score": "+0.45", "engine_rank": 1},
            {"move": "Nd2", "rationale": "Rerouting knight to better square",
             "engine_score": "+0.22", "engine_rank": 3},
            {"move": "Re1", "rationale": "Controls the open e-file",
             "engine_score": "+0.35", "engine_rank": 2},
        ])
        assert s.candidate_moves[0].engine_score == "+0.45"
        assert s.candidate_moves[0].engine_rank == 1

    def test_candidate_move_without_engine_score(self):
        """Engine fields are optional — analysis works without engine."""
        s = make_synthesis()
        assert s.candidate_moves[0].engine_score is None
        assert s.candidate_moves[0].engine_rank is None

    def test_too_few_moves(self):
        with pytest.raises(ValidationError, match="candidate_moves"):
            make_synthesis(candidate_moves=[
                {"move": "Bf4", "rationale": "Activates the bishop toward e5"},
                {"move": "Nd2", "rationale": "Rerouting knight to better square"},
            ])

    def test_too_many_moves(self):
        with pytest.raises(ValidationError, match="candidate_moves"):
            make_synthesis(candidate_moves=[
                {"move": f"Move{i}", "rationale": f"Rationale for move {i} here"}
                for i in range(1, 7)
            ])

    def test_too_few_imbalances(self):
        with pytest.raises(ValidationError, match="key_imbalances"):
            make_synthesis(key_imbalances=[])

    def test_k0_revision_too_short(self):
        with pytest.raises(ValidationError, match="k0_revision"):
            make_synthesis(k0_revision="Short")


# ── TestDiscomfortHeuristic ──────────────────────────────────────────────────

class TestDiscomfortHeuristic:
    def test_valid(self):
        dh = make_discomfort_heuristic()
        assert dh.feels_comfortable is False
        assert dh.warning is None

    def test_comfort_warning_added(self):
        """comfortable + not more uncertain → auto-populate warning."""
        dh = DiscomfortHeuristic(
            feels_comfortable=True,
            confidence_drop_moment="None noticed",
            more_uncertain_than_start=False,
            warning=None,
        )
        assert dh.warning is not None
        assert len(dh.warning) > 0

    def test_no_warning_when_uncertain(self):
        """comfortable but more uncertain → no auto-warning needed."""
        dh = DiscomfortHeuristic(
            feels_comfortable=True,
            confidence_drop_moment="Early on when reviewing tactics",
            more_uncertain_than_start=True,
            warning=None,
        )
        assert dh.warning is None


# ── TestBFIHAnalysis ─────────────────────────────────────────────────────────

class TestBFIHAnalysis:
    def test_full_composite(self):
        analysis = BFIHAnalysis(
            fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
            k0=make_k0(),
            hypotheses=make_hypothesis_set(),
            ontological_scan=make_ontological_scan(),
            ancestral_check=make_ancestral_check(),
            paradigm_inversion=make_paradigm_inversion(),
            evidence_matrix=make_evidence_matrix(),
            reflexive_review=make_reflexive_review(),
            synthesis=make_synthesis(),
            discomfort_heuristic=make_discomfort_heuristic(),
        )
        assert analysis.fen is not None
        assert analysis.k0.paradigm == Paradigm.dynamic
        assert len(analysis.ontological_scan.findings) == 10
