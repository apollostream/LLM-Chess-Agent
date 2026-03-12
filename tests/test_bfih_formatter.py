"""Tests for BFIH formatter CLI — TDD Red phase.

Tests per-phase rendering, full render, and summary output.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "chess-imbalances" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bfih_formatter import (
    render_k0, render_hypotheses, render_ontological_scan,
    render_ancestral_check, render_paradigm_inversion,
    render_evidence_matrix, render_reflexive_review,
    render_synthesis, render_discomfort_heuristic,
    render_full, render_summary,
)
from test_bfih_models import (
    make_k0, make_hypothesis_set, make_ontological_scan,
    make_ancestral_check, make_paradigm_inversion, make_evidence_matrix,
    make_reflexive_review, make_synthesis, make_discomfort_heuristic,
)

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "chess-imbalances" / "scripts"
FORMATTER = SCRIPTS_DIR / "bfih_formatter.py"
PYTHON = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"


def populate_phases_dir(tmpdir: Path) -> Path:
    """Write all 9 valid phases to a directory."""
    phases_dir = tmpdir / "bfih_phases"
    phases_dir.mkdir(exist_ok=True)
    models = {
        1: make_k0(), 2: make_hypothesis_set(), 3: make_ontological_scan(),
        4: make_ancestral_check(), 5: make_paradigm_inversion(),
        6: make_evidence_matrix(), 7: make_reflexive_review(),
        8: make_synthesis(), 9: make_discomfort_heuristic(),
    }
    for num, model in models.items():
        (phases_dir / f"phase_{num}.json").write_text(model.model_dump_json(indent=2))
    return phases_dir


# ── TestPhaseRendering ───────────────────────────────────────────────────────

class TestPhaseRendering:
    def test_render_k0(self):
        md = render_k0(make_k0())
        assert "K₀" in md or "K0" in md
        assert "dynamic" in md
        assert "moderate" in md

    def test_render_hypotheses(self):
        md = render_hypotheses(make_hypothesis_set())
        assert "H1" in md
        assert "H_catch" in md
        assert "0.45" in md or "45" in md

    def test_render_ontological_scan(self):
        md = render_ontological_scan(make_ontological_scan())
        assert "Superior Minor Piece" in md or "Imbalance 1" in md
        # Should cover all 10
        for i in range(1, 11):
            assert str(i) in md

    def test_render_ancestral_check(self):
        md = render_ancestral_check(make_ancestral_check())
        assert "Carlsbad" in md
        assert "Karpov" in md or "paradigm" in md.lower()

    def test_render_paradigm_inversion(self):
        md = render_paradigm_inversion(make_paradigm_inversion())
        assert "black" in md.lower() or "inversion" in md.lower()
        assert "probability" in md.lower() or "shift" in md.lower()

    def test_render_evidence_matrix(self):
        md = render_evidence_matrix(make_evidence_matrix())
        # Should have a table with ++ and -- style ratings
        assert "++" in md
        assert "|" in md  # Table structure
        # Should show prior→posterior
        assert "0.45" in md or "0.40" in md

    def test_render_reflexive_review(self):
        md = render_reflexive_review(make_reflexive_review())
        assert "red team" in md.lower() or "Red Team" in md
        assert "surprising" in md.lower()

    def test_render_synthesis(self):
        md = render_synthesis(make_synthesis())
        assert "white_slight" in md or "White slight" in md.lower() or "slight" in md.lower()
        assert "Bf4" in md or "candidate" in md.lower()

    def test_render_discomfort_heuristic(self):
        md = render_discomfort_heuristic(make_discomfort_heuristic())
        assert "discomfort" in md.lower() or "comfortable" in md.lower()


# ── TestFullRender ───────────────────────────────────────────────────────────

class TestFullRender:
    def test_full_render(self, tmp_path):
        phases_dir = populate_phases_dir(tmp_path)
        md = render_full(phases_dir)
        # Should contain all major sections
        assert "K₀" in md or "K0" in md
        assert "Hypothes" in md
        assert "Ontological" in md or "Imbalance" in md
        assert "Synthesis" in md

    def test_full_render_with_position(self, tmp_path):
        phases_dir = populate_phases_dir(tmp_path)
        position_data = {
            "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
            "side_to_move": "black",
        }
        md = render_full(phases_dir, position_data=position_data)
        assert "rnbqkbnr" in md or "FEN" in md


# ── TestSummary ──────────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_format(self, tmp_path):
        phases_dir = populate_phases_dir(tmp_path)
        summary = render_summary(phases_dir)
        # Should be concise — not the full render
        assert len(summary) < 2000
        # Should mention assessment
        assert "white" in summary.lower() or "slight" in summary.lower() or "assessment" in summary.lower()
