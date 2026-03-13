"""Tests for BFIH validator CLI — TDD Red phase.

Tests validate-phase, validate-all, cross-phase gates, and CLI interface.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude" / "skills" / "chess-imbalances" / "scripts"))

from bfih_validator import (
    validate_phase, validate_all, export_schema,
    gate_g2, gate_g5, gate_g6, gate_g8,
    GateResult,
)
from bfih_models import (
    K0, HypothesisSet, OntologicalScan, AncestralCheck,
    ParadigmInversion, EvidenceMatrix, ReflexiveReview,
    Synthesis, DiscomfortHeuristic,
)

# Reuse test helpers from model tests
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_bfih_models import (
    make_k0, make_hypothesis_set, make_ontological_scan,
    make_ancestral_check, make_paradigm_inversion, make_evidence_matrix,
    make_reflexive_review, make_synthesis, make_discomfort_heuristic,
)

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "chess-imbalances" / "scripts"
VALIDATOR = SCRIPTS_DIR / "bfih_validator.py"
PYTHON = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"


# ── Helpers ──────────────────────────────────────────────────────────────────

def write_phase_json(tmpdir: Path, phase_num: int, data: dict) -> Path:
    """Write phase data as JSON file and return path."""
    path = tmpdir / f"phase_{phase_num}.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def populate_phases_dir(tmpdir: Path, phases: dict[int, object]) -> Path:
    """Write multiple phase model instances to a directory."""
    phases_dir = tmpdir / "bfih_phases"
    phases_dir.mkdir(exist_ok=True)
    for num, model in phases.items():
        path = phases_dir / f"phase_{num}.json"
        path.write_text(model.model_dump_json(indent=2))
    return phases_dir


# ── TestValidatePhase ────────────────────────────────────────────────────────

class TestValidatePhase:
    def test_valid_phase(self, tmp_path):
        k0 = make_k0()
        path = write_phase_json(tmp_path, 1, k0.model_dump())
        result = validate_phase(1, path)
        assert result["valid"] is True

    def test_invalid_phase(self, tmp_path):
        path = write_phase_json(tmp_path, 1, {"opening_context": "Short"})
        result = validate_phase(1, path)
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_unknown_phase(self, tmp_path):
        path = write_phase_json(tmp_path, 99, {})
        result = validate_phase(99, path)
        assert result["valid"] is False
        assert "unknown phase" in result["errors"][0].lower()

    def test_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        result = validate_phase(1, path)
        assert result["valid"] is False
        assert "not found" in result["errors"][0].lower()

    def test_malformed_json(self, tmp_path):
        path = tmp_path / "phase_1.json"
        path.write_text("{bad json")
        result = validate_phase(1, path)
        assert result["valid"] is False
        assert "json" in result["errors"][0].lower()

    def test_schema_export(self):
        schema = export_schema(3)
        assert "OntologicalScan" in schema or "findings" in schema


# ── TestCrossPhaseGates ──────────────────────────────────────────────────────

class TestCrossPhaseGates:
    def test_g2_pass(self):
        """At least one hypothesis differs from K0 assessment."""
        k0 = make_k0(gut_read_assessment="white_slight")
        hs = make_hypothesis_set()  # Has equal and black_slight hypotheses
        result = gate_g2(k0, hs)
        assert result.passed is True

    def test_g2_fail(self):
        """All hypotheses match K0 direction → fail."""
        k0 = make_k0(gut_read_assessment="white_slight")
        hs = make_hypothesis_set(hypotheses=[
            {"id": "H1", "prior": 0.50, "assessment": "white_slight",
             "description": "White is slightly better due to space",
             "plan": "Expand on kingside"},
            {"id": "H2", "prior": 0.30, "assessment": "white_clear",
             "description": "White has clear advantage in this position",
             "plan": "Press the advantage"},
            {"id": "H_catch", "prior": 0.20, "assessment": "white_decisive",
             "description": "White has decisive advantage position",
             "plan": "Find the winning continuation"},
        ])
        result = gate_g2(k0, hs)
        assert result.passed is False

    def test_g5_pass(self):
        """Inverted assessment differs in direction from K0."""
        k0 = make_k0(gut_read_assessment="white_slight")
        pi = make_paradigm_inversion(inverted_assessment="black_slight")
        result = gate_g5(k0, pi)
        assert result.passed is True

    def test_g5_fail(self):
        """Inverted assessment same direction as K0 → fail."""
        k0 = make_k0(gut_read_assessment="white_slight")
        pi = make_paradigm_inversion(inverted_assessment="white_clear")
        result = gate_g5(k0, pi)
        assert result.passed is False

    def test_g6_pass(self):
        """At least one posterior moved >0.05 from prior."""
        em = make_evidence_matrix()  # Default has H3: 0.15→0.20
        result = gate_g6(em)
        assert result.passed is True

    def test_g6_fail(self):
        """No posterior moved >0.05 → fail."""
        em = make_evidence_matrix(posteriors=[
            {"hypothesis_id": "H1", "prior": 0.45, "posterior": 0.44,
             "reasoning": "Barely changed from initial prior assessment"},
            {"hypothesis_id": "H2", "prior": 0.30, "posterior": 0.31,
             "reasoning": "Barely changed from initial prior assessment"},
            {"hypothesis_id": "H3", "prior": 0.15, "posterior": 0.15,
             "reasoning": "Unchanged from initial prior assessment here"},
            {"hypothesis_id": "H_catch", "prior": 0.10, "posterior": 0.10,
             "reasoning": "Unchanged from initial prior assessment here"},
        ])
        result = gate_g6(em)
        assert result.passed is False

    def test_g8_pass(self):
        """All candidate moves are legal."""
        s = make_synthesis(candidate_moves=[
            {"move": "e4", "rationale": "Opens the center for piece play"},
            {"move": "d4", "rationale": "Controls center and opens lines"},
            {"move": "Nf3", "rationale": "Develops knight toward center"},
        ])
        legal_moves = ["e4", "d4", "Nf3", "Nc3", "a3", "b3"]
        result = gate_g8(s, legal_moves)
        assert result.passed is True

    def test_g8_fail(self):
        """Candidate move not in legal moves → fail."""
        s = make_synthesis(candidate_moves=[
            {"move": "e4", "rationale": "Opens the center for piece play"},
            {"move": "Qxh7#", "rationale": "Checkmate if it were legal here"},
            {"move": "Nf3", "rationale": "Develops knight toward center"},
        ])
        legal_moves = ["e4", "d4", "Nf3", "Nc3"]
        result = gate_g8(s, legal_moves)
        assert result.passed is False
        assert "Qxh7#" in result.message


# ── TestValidateAll ──────────────────────────────────────────────────────────

class TestValidateAll:
    def test_complete(self, tmp_path):
        phases = {
            1: make_k0(),
            2: make_hypothesis_set(),
            3: make_ontological_scan(),
            4: make_ancestral_check(),
            5: make_paradigm_inversion(),
            6: make_evidence_matrix(),
            7: make_reflexive_review(),
            8: make_synthesis(),
            9: make_discomfort_heuristic(),
        }
        phases_dir = populate_phases_dir(tmp_path, phases)
        result = validate_all(phases_dir)
        assert result["valid"] is True

    def test_missing_phase(self, tmp_path):
        phases = {
            1: make_k0(),
            2: make_hypothesis_set(),
            # Missing 3-9
        }
        phases_dir = populate_phases_dir(tmp_path, phases)
        result = validate_all(phases_dir)
        assert result["valid"] is False
        assert any("missing" in e.lower() or "not found" in e.lower()
                    for e in result["errors"])

    def test_partial_failure(self, tmp_path):
        """Valid phase 1, invalid phase 2."""
        phases_dir = tmp_path / "bfih_phases"
        phases_dir.mkdir()
        # Valid phase 1
        (phases_dir / "phase_1.json").write_text(make_k0().model_dump_json(indent=2))
        # Invalid phase 2
        (phases_dir / "phase_2.json").write_text(json.dumps({"hypotheses": []}))
        result = validate_all(phases_dir)
        assert result["valid"] is False

    def test_gate_failures(self, tmp_path):
        """All phases valid but cross-phase gate G2 fails."""
        k0 = make_k0(gut_read_assessment="white_slight")
        # All hypotheses favor White → G2 should fail
        hs = make_hypothesis_set(hypotheses=[
            {"id": "H1", "prior": 0.50, "assessment": "white_slight",
             "description": "White is slightly better due to space",
             "plan": "Expand on kingside"},
            {"id": "H2", "prior": 0.30, "assessment": "white_clear",
             "description": "White has clear advantage in this position",
             "plan": "Press the advantage"},
            {"id": "H_catch", "prior": 0.20, "assessment": "white_decisive",
             "description": "White has decisive advantage position",
             "plan": "Find the winning continuation"},
        ])
        phases = {
            1: k0, 2: hs, 3: make_ontological_scan(),
            4: make_ancestral_check(), 5: make_paradigm_inversion(),
            6: make_evidence_matrix(), 7: make_reflexive_review(),
            8: make_synthesis(), 9: make_discomfort_heuristic(),
        }
        phases_dir = populate_phases_dir(tmp_path, phases)
        result = validate_all(phases_dir)
        assert result["valid"] is False
        assert any("G2" in gf for gf in result.get("gate_failures", []))


# ── TestCLI ──────────────────────────────────────────────────────────────────

class TestCLI:
    def test_validate_phase_cli(self, tmp_path):
        k0 = make_k0()
        path = write_phase_json(tmp_path, 1, k0.model_dump())
        result = subprocess.run(
            [str(PYTHON), str(VALIDATOR), "validate-phase", "1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "VALID" in result.stdout

    def test_validate_all_cli(self, tmp_path):
        phases = {
            1: make_k0(), 2: make_hypothesis_set(),
            3: make_ontological_scan(), 4: make_ancestral_check(),
            5: make_paradigm_inversion(), 6: make_evidence_matrix(),
            7: make_reflexive_review(), 8: make_synthesis(),
            9: make_discomfort_heuristic(),
        }
        phases_dir = populate_phases_dir(tmp_path, phases)
        result = subprocess.run(
            [str(PYTHON), str(VALIDATOR), "validate-all", str(phases_dir)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_schema_cli(self):
        result = subprocess.run(
            [str(PYTHON), str(VALIDATOR), "schema", "3"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "findings" in result.stdout

    def test_help_cli(self):
        result = subprocess.run(
            [str(PYTHON), str(VALIDATOR), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "validate-phase" in result.stdout
