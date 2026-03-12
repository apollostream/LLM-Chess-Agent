"""Pydantic v2 models for the 9 BFIH analysis phases.

Each phase has validation constraints that enforce the BFIH protocol:
minimum-length fields prevent shallow analysis, probability sum checks
ensure coherent Bayesian reasoning, and quality gates catch straw-man
paradigm inversions.
"""

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ── Enums ────────────────────────────────────────────────────────────────────

class Paradigm(StrEnum):
    positional = "positional"
    dynamic = "dynamic"
    transitional = "transitional"
    universal = "universal"


class Confidence(StrEnum):
    speculative = "speculative"
    moderate = "moderate"
    confident = "confident"
    very_confident = "very_confident"


class Relevance(StrEnum):
    high = "high"
    moderate = "moderate"
    low = "low"


class Direction(StrEnum):
    white = "white"
    black = "black"
    neutral = "neutral"


class Likelihood(StrEnum):
    strongly_expected = "++"
    consistent = "+"
    neutral = "0"
    somewhat_surprising = "-"
    very_surprising = "--"


class Assessment(StrEnum):
    white_decisive = "white_decisive"
    white_clear = "white_clear"
    white_slight = "white_slight"
    equal = "equal"
    black_slight = "black_slight"
    black_clear = "black_clear"
    black_decisive = "black_decisive"


# ── Phase 1: K0 ─────────────────────────────────────────────────────────────

class K0(BaseModel):
    """Phase 1 — Initial state declaration before analysis."""
    opening_context: str = Field(min_length=10)
    paradigm: Paradigm
    gut_read: str = Field(min_length=20)
    gut_read_assessment: Assessment
    confidence: Confidence
    disconfirming_triggers: list[str] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def validate_trigger_lengths(self):
        for i, trigger in enumerate(self.disconfirming_triggers):
            if len(trigger) < 15:
                raise ValueError(
                    f"disconfirming_triggers[{i}] must be at least 15 characters, "
                    f"got {len(trigger)}"
                )
        return self


# ── Phase 2: Hypotheses ──────────────────────────────────────────────────────

class Hypothesis(BaseModel):
    """A single competing hypothesis with prior probability."""
    id: str = Field(pattern=r"^H\d+$|^H_catch$")
    prior: float = Field(ge=0.0, le=1.0)
    assessment: Assessment
    description: str = Field(min_length=20)
    plan: str = Field(min_length=10)


class HypothesisSet(BaseModel):
    """Phase 2 — Set of 2-5 competing hypotheses."""
    hypotheses: list[Hypothesis] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def validate_hypothesis_set(self):
        ids = [h.id for h in self.hypotheses]
        if len(ids) != len(set(ids)):
            raise ValueError("Hypothesis IDs must be unique")
        if "H_catch" not in ids:
            raise ValueError("H_catch hypothesis is required")
        total = sum(h.prior for h in self.hypotheses)
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Hypothesis priors must sum to 1.0 (±0.01), got {total:.3f}"
            )
        return self


# ── Phase 3: Ontological Scan ────────────────────────────────────────────────

class ImbalanceFinding(BaseModel):
    """A single imbalance finding from the 10-category scan."""
    number: int = Field(ge=1, le=10)
    name: str
    finding: str = Field(min_length=10)
    relevance: Relevance
    direction: Direction
    interaction: str


class OntologicalScan(BaseModel):
    """Phase 3 — All 10 imbalance categories scanned."""
    findings: list[ImbalanceFinding] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def validate_all_10_present(self):
        numbers = [f.number for f in self.findings]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Imbalance finding numbers must be unique")
        if set(numbers) != set(range(1, 11)):
            raise ValueError("Findings must cover all imbalances 1 through 10")
        return self


# ── Phase 4: Ancestral Check ────────────────────────────────────────────────

class AncestralCheck(BaseModel):
    """Phase 4 — Historical and paradigmatic context."""
    structural_analogy: str = Field(min_length=20)
    paradigm_precedent: str = Field(min_length=20)
    engine_vs_human: str
    historical_pitfalls: str


# ── Phase 5: Paradigm Inversion ─────────────────────────────────────────────

class ParadigmInversion(BaseModel):
    """Phase 5 — Forced counter-argument to K0."""
    inverted_argument: str = Field(min_length=80)
    inverted_assessment: Assessment
    new_considerations: list[str] = Field(min_length=1)
    felt_easy_to_dismiss: bool
    probability_shift: float

    @model_validator(mode="after")
    def validate_quality_gate(self):
        if self.felt_easy_to_dismiss and abs(self.probability_shift) < 0.05:
            raise ValueError(
                "Paradigm inversion quality gate failed: felt easy to dismiss "
                "AND probability shift < 0.05 — try harder"
            )
        return self


# ── Phase 6: Evidence Matrix ────────────────────────────────────────────────

class EvidenceRow(BaseModel):
    """A single row in the evidence matrix."""
    finding: str
    ratings: dict[str, Likelihood]


class PosteriorUpdate(BaseModel):
    """Updated probability for a hypothesis after evidence review."""
    hypothesis_id: str
    prior: float = Field(ge=0.0, le=1.0)
    posterior: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=20)


class EvidenceMatrix(BaseModel):
    """Phase 6 — Evidence matrix with posterior updates."""
    rows: list[EvidenceRow] = Field(min_length=3)
    posteriors: list[PosteriorUpdate]

    @model_validator(mode="after")
    def validate_posteriors_sum(self):
        total = sum(p.posterior for p in self.posteriors)
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Posterior probabilities must sum to 1.0 (±0.01), got {total:.3f}"
            )
        return self


# ── Phase 7: Reflexive Review ───────────────────────────────────────────────

class ReflexiveReview(BaseModel):
    """Phase 7 — Self-examination and red-teaming."""
    k0_comparison: str
    most_surprising_finding: str
    paradigm_sensitivity: str
    red_team_argument: str = Field(min_length=40)
    genuine_update: bool


# ── Phase 8: Synthesis ──────────────────────────────────────────────────────

class CandidateMove(BaseModel):
    """A candidate move with strategic rationale."""
    move: str
    rationale: str = Field(min_length=10)


class Synthesis(BaseModel):
    """Phase 8 — Final synthesized assessment."""
    assessment: Assessment
    confidence: Confidence
    key_imbalances: list[str] = Field(min_length=1, max_length=4)
    paradigm_note: str
    k0_revision: str = Field(min_length=20)
    disconfirming_evidence: list[str] = Field(min_length=1)
    candidate_moves: list[CandidateMove] = Field(min_length=3, max_length=5)


# ── Phase 9: Discomfort Heuristic ───────────────────────────────────────────

class DiscomfortHeuristic(BaseModel):
    """Phase 9 — Final quality check on intellectual honesty."""
    feels_comfortable: bool
    confidence_drop_moment: str
    more_uncertain_than_start: bool
    warning: Optional[str] = None

    @model_validator(mode="after")
    def validate_comfort_warning(self):
        if self.feels_comfortable and not self.more_uncertain_than_start:
            if not self.warning:
                self.warning = (
                    "Analysis feels comfortable and no increase in uncertainty — "
                    "paradigm inversion may have been insufficient"
                )
        return self


# ── Composite ───────────────────────────────────────────────────────────────

class BFIHAnalysis(BaseModel):
    """Complete BFIH analysis across all 9 phases."""
    fen: str
    k0: K0
    hypotheses: HypothesisSet
    ontological_scan: OntologicalScan
    ancestral_check: AncestralCheck
    paradigm_inversion: ParadigmInversion
    evidence_matrix: EvidenceMatrix
    reflexive_review: ReflexiveReview
    synthesis: Synthesis
    discomfort_heuristic: DiscomfortHeuristic
