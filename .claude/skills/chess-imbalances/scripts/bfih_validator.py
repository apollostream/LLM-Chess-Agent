#!/usr/bin/env python3
"""BFIH phase validator CLI.

Validates individual phase JSON files against Pydantic models and enforces
cross-phase gates (G2, G5, G6, G8). Used by Claude Code during --deep analysis
to ensure each phase meets BFIH protocol requirements.

Usage:
    python bfih_validator.py validate-phase 1 phase_1.json
    python bfih_validator.py validate-phase 6 phase_6.json --prior-phases dir/
    python bfih_validator.py validate-phase 8 phase_8.json --prior-phases dir/ --position-data pos.json
    python bfih_validator.py validate-all dir/ --position-data pos.json
    python bfih_validator.py schema 3
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from bfih_models import (
    K0, HypothesisSet, OntologicalScan, AncestralCheck,
    ParadigmInversion, EvidenceMatrix, ReflexiveReview,
    Synthesis, DiscomfortHeuristic, Assessment,
)

PHASE_MODELS = {
    1: K0,
    2: HypothesisSet,
    3: OntologicalScan,
    4: AncestralCheck,
    5: ParadigmInversion,
    6: EvidenceMatrix,
    7: ReflexiveReview,
    8: Synthesis,
    9: DiscomfortHeuristic,
}

PHASE_NAMES = {
    1: "K0", 2: "HypothesisSet", 3: "OntologicalScan",
    4: "AncestralCheck", 5: "ParadigmInversion", 6: "EvidenceMatrix",
    7: "ReflexiveReview", 8: "Synthesis", 9: "DiscomfortHeuristic",
}


# ── Gate results ─────────────────────────────────────────────────────────────

@dataclass
class GateResult:
    gate: str
    passed: bool
    message: str


# ── Assessment direction helpers ─────────────────────────────────────────────

def _assessment_direction(assessment: Assessment) -> str:
    """Return 'white', 'black', or 'equal' for an assessment."""
    if assessment in (Assessment.white_decisive, Assessment.white_clear, Assessment.white_slight):
        return "white"
    elif assessment in (Assessment.black_decisive, Assessment.black_clear, Assessment.black_slight):
        return "black"
    return "equal"


# ── Cross-phase gates ───────────────────────────────────────────────────────

def gate_g2(k0: K0, hypotheses: HypothesisSet) -> GateResult:
    """G2: At least one hypothesis assessment differs from K0's direction."""
    k0_dir = _assessment_direction(k0.gut_read_assessment)
    for h in hypotheses.hypotheses:
        if _assessment_direction(h.assessment) != k0_dir:
            return GateResult("G2", True, "At least one hypothesis challenges K0")
    return GateResult(
        "G2", False,
        f"All hypotheses agree with K0 direction ({k0_dir}) — "
        "at least one must differ"
    )


def gate_g5(k0: K0, inversion: ParadigmInversion) -> GateResult:
    """G5: Inverted assessment differs in direction from K0."""
    k0_dir = _assessment_direction(k0.gut_read_assessment)
    inv_dir = _assessment_direction(inversion.inverted_assessment)
    if inv_dir != k0_dir:
        return GateResult("G5", True, "Inversion argues a different direction")
    return GateResult(
        "G5", False,
        f"Inverted assessment ({inversion.inverted_assessment}) has same direction "
        f"as K0 ({k0.gut_read_assessment}) — inversion must argue the other side"
    )


def gate_g6(evidence_matrix: EvidenceMatrix) -> GateResult:
    """G6: At least one posterior moved >0.05 from its prior."""
    for p in evidence_matrix.posteriors:
        if abs(p.posterior - p.prior) > 0.05:
            return GateResult("G6", True, f"{p.hypothesis_id} moved {abs(p.posterior - p.prior):.2f}")
    return GateResult(
        "G6", False,
        "No posterior moved >0.05 from prior — evidence matrix had no effect"
    )


def gate_g8(synthesis: Synthesis, legal_moves: list[str]) -> GateResult:
    """G8: All candidate moves must be in the legal moves list."""
    illegal = [cm.move for cm in synthesis.candidate_moves if cm.move not in legal_moves]
    if not illegal:
        return GateResult("G8", True, "All candidate moves are legal")
    return GateResult(
        "G8", False,
        f"Illegal candidate moves: {', '.join(illegal)}"
    )


# ── Validation functions ────────────────────────────────────────────────────

def validate_phase(phase_num: int, path: Path,
                   prior_phases_dir: Path | None = None,
                   position_data: dict | None = None) -> dict:
    """Validate a single phase JSON file.

    Returns dict with 'valid', 'errors', and optionally 'gate_failures'.
    """
    if phase_num not in PHASE_MODELS:
        return {"phase": phase_num, "valid": False,
                "errors": [f"Unknown phase number: {phase_num}"], "gate_failures": []}

    path = Path(path)
    if not path.exists():
        return {"phase": phase_num, "valid": False,
                "errors": [f"File not found: {path}"], "gate_failures": []}

    try:
        raw = path.read_text()
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"phase": phase_num, "valid": False,
                "errors": [f"JSON parse error: {e}"], "gate_failures": []}

    model_cls = PHASE_MODELS[phase_num]
    try:
        model = model_cls(**data)
    except ValidationError as e:
        errors = [err["msg"] for err in e.errors()]
        return {"phase": phase_num, "valid": False,
                "errors": errors, "gate_failures": []}

    # Cross-phase gates
    gate_failures = []
    if prior_phases_dir:
        gate_failures = _run_gates(phase_num, model, prior_phases_dir, position_data)

    return {
        "phase": phase_num,
        "valid": len(gate_failures) == 0,
        "errors": [],
        "gate_failures": [f"{g.gate}: {g.message}" for g in gate_failures if not g.passed],
    }


def _load_prior_phase(phases_dir: Path, phase_num: int):
    """Load and parse a prior phase from the phases directory."""
    path = phases_dir / f"phase_{phase_num}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return PHASE_MODELS[phase_num](**data)


def _run_gates(phase_num: int, model, phases_dir: Path,
               position_data: dict | None) -> list[GateResult]:
    """Run applicable cross-phase gates for the given phase."""
    failures = []

    if phase_num == 2:
        k0 = _load_prior_phase(phases_dir, 1)
        if k0:
            result = gate_g2(k0, model)
            if not result.passed:
                failures.append(result)

    elif phase_num == 5:
        k0 = _load_prior_phase(phases_dir, 1)
        if k0:
            result = gate_g5(k0, model)
            if not result.passed:
                failures.append(result)

    elif phase_num == 6:
        result = gate_g6(model)
        if not result.passed:
            failures.append(result)

    elif phase_num == 8:
        if position_data and "legal_moves" in position_data:
            result = gate_g8(model, position_data["legal_moves"])
            if not result.passed:
                failures.append(result)

    return failures


def validate_all(phases_dir: Path, position_data: dict | None = None) -> dict:
    """Validate all 9 phases and run cross-phase gates.

    Returns dict with 'valid', 'errors', 'gate_failures', and per-phase results.
    """
    phases_dir = Path(phases_dir)
    all_errors = []
    all_gate_failures = []
    phase_results = {}

    for phase_num in range(1, 10):
        path = phases_dir / f"phase_{phase_num}.json"
        result = validate_phase(phase_num, path, prior_phases_dir=phases_dir,
                                position_data=position_data)
        phase_results[phase_num] = result
        if not result["valid"]:
            all_errors.extend(
                f"Phase {phase_num}: {e}" for e in result["errors"]
            )
            all_gate_failures.extend(result.get("gate_failures", []))

    return {
        "valid": len(all_errors) == 0 and len(all_gate_failures) == 0,
        "errors": all_errors,
        "gate_failures": all_gate_failures,
        "phases": phase_results,
    }


def export_schema(phase_num: int) -> str:
    """Export JSON schema for a phase model."""
    if phase_num not in PHASE_MODELS:
        return json.dumps({"error": f"Unknown phase: {phase_num}"})
    return json.dumps(PHASE_MODELS[phase_num].model_json_schema(), indent=2)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Validate BFIH phase JSON files and enforce cross-phase gates."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate-phase
    vp = subparsers.add_parser("validate-phase", help="Validate a single phase")
    vp.add_argument("phase", type=int, help="Phase number (1-9)")
    vp.add_argument("file", help="Path to phase JSON file")
    vp.add_argument("--prior-phases", help="Directory containing prior phase files")
    vp.add_argument("--position-data", help="Path to position data JSON (for G8)")

    # validate-all
    va = subparsers.add_parser("validate-all", help="Validate all phases in a directory")
    va.add_argument("dir", help="Directory containing phase_N.json files")
    va.add_argument("--position-data", help="Path to position data JSON (for G8)")

    # schema
    sc = subparsers.add_parser("schema", help="Export JSON schema for a phase")
    sc.add_argument("phase", type=int, help="Phase number (1-9)")

    args = parser.parse_args()

    if args.command == "validate-phase":
        position_data = None
        if hasattr(args, "position_data") and args.position_data:
            position_data = json.loads(Path(args.position_data).read_text())

        prior_dir = Path(args.prior_phases) if args.prior_phases else None
        result = validate_phase(args.phase, Path(args.file),
                                prior_phases_dir=prior_dir,
                                position_data=position_data)

        if result["valid"]:
            print(f"VALID: Phase {args.phase} passed all checks")
            sys.exit(0)
        else:
            print(json.dumps(result, indent=2), file=sys.stderr)
            sys.exit(1)

    elif args.command == "validate-all":
        position_data = None
        if hasattr(args, "position_data") and args.position_data:
            position_data = json.loads(Path(args.position_data).read_text())

        result = validate_all(Path(args.dir), position_data=position_data)

        if result["valid"]:
            print("VALID: All 9 phases passed validation and gates")
            sys.exit(0)
        else:
            print(json.dumps(result, indent=2), file=sys.stderr)
            sys.exit(1)

    elif args.command == "schema":
        print(export_schema(args.phase))
        sys.exit(0)


if __name__ == "__main__":
    main()
