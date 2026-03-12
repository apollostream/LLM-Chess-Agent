#!/usr/bin/env python3
"""BFIH formatter CLI.

Renders validated BFIH phase JSON files to markdown output. Used by Claude Code
after all phases are validated to produce the final deep analysis document.

Usage:
    python bfih_formatter.py render dir/ --position-data pos.json --output file.md
    python bfih_formatter.py summary dir/
"""

import argparse
import json
import sys
from pathlib import Path

from bfih_models import (
    K0, HypothesisSet, OntologicalScan, AncestralCheck,
    ParadigmInversion, EvidenceMatrix, ReflexiveReview,
    Synthesis, DiscomfortHeuristic,
)

PHASE_MODELS = {
    1: K0, 2: HypothesisSet, 3: OntologicalScan, 4: AncestralCheck,
    5: ParadigmInversion, 6: EvidenceMatrix, 7: ReflexiveReview,
    8: Synthesis, 9: DiscomfortHeuristic,
}


def _load_phase(phases_dir: Path, phase_num: int):
    """Load and parse a phase JSON file."""
    path = phases_dir / f"phase_{phase_num}.json"
    data = json.loads(path.read_text())
    return PHASE_MODELS[phase_num](**data)


def _assessment_display(assessment: str) -> str:
    """Human-readable assessment."""
    return assessment.replace("_", " ").title()


# ── Per-phase renderers ─────────────────────────────────────────────────────

def render_k0(k0: K0) -> str:
    lines = [
        "### K₀ — Initial State",
        "",
        f"- **Context:** {k0.opening_context}",
        f"- **Paradigm:** {k0.paradigm.value}",
        f"- **Gut read:** {k0.gut_read}",
        f"- **Assessment:** {_assessment_display(k0.gut_read_assessment.value)}",
        f"- **Confidence:** {k0.confidence.value}",
        "- **Disconfirming triggers:**",
    ]
    for trigger in k0.disconfirming_triggers:
        lines.append(f"  - {trigger}")
    return "\n".join(lines)


def render_hypotheses(hs: HypothesisSet) -> str:
    lines = ["### Hypotheses", ""]
    for h in hs.hypotheses:
        lines.append(
            f"**{h.id}** (prior: {h.prior:.2f}) — "
            f"{_assessment_display(h.assessment.value)}"
        )
        lines.append(f"  {h.description}")
        lines.append(f"  *Plan:* {h.plan}")
        lines.append("")
    return "\n".join(lines)


def render_ontological_scan(scan: OntologicalScan) -> str:
    lines = ["### Ontological Scan — 10 Imbalances", ""]
    for f in sorted(scan.findings, key=lambda x: x.number):
        lines.append(
            f"**{f.number}. {f.name}** "
            f"[{f.relevance.value}] [{f.direction.value}]"
        )
        lines.append(f"  {f.finding}")
        if f.interaction:
            lines.append(f"  *Interaction:* {f.interaction}")
        lines.append("")
    return "\n".join(lines)


def render_ancestral_check(ac: AncestralCheck) -> str:
    lines = [
        "### Ancestral Check",
        "",
        f"- **Structural analogy:** {ac.structural_analogy}",
        f"- **Paradigm precedent:** {ac.paradigm_precedent}",
        f"- **Engine vs human:** {ac.engine_vs_human}",
        f"- **Historical pitfalls:** {ac.historical_pitfalls}",
    ]
    return "\n".join(lines)


def render_paradigm_inversion(pi: ParadigmInversion) -> str:
    lines = [
        "### Paradigm Inversion",
        "",
        f"**Inverted assessment:** {_assessment_display(pi.inverted_assessment.value)}",
        "",
        pi.inverted_argument,
        "",
        f"- **Felt easy to dismiss:** {'Yes' if pi.felt_easy_to_dismiss else 'No'}",
        f"- **Probability shift:** {pi.probability_shift:+.2f}",
        "- **New considerations:**",
    ]
    for c in pi.new_considerations:
        lines.append(f"  - {c}")
    return "\n".join(lines)


def render_evidence_matrix(em: EvidenceMatrix) -> str:
    lines = ["### Evidence Matrix", ""]

    # Build header from hypothesis IDs in posteriors
    h_ids = [p.hypothesis_id for p in em.posteriors]
    prior_map = {p.hypothesis_id: p.prior for p in em.posteriors}
    posterior_map = {p.hypothesis_id: p.posterior for p in em.posteriors}

    header_cells = ["Finding"]
    for h_id in h_ids:
        p = prior_map.get(h_id, 0)
        post = posterior_map.get(h_id, 0)
        header_cells.append(f"{h_id} ({p:.2f}→{post:.2f})")

    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("| " + " | ".join("---" for _ in header_cells) + " |")

    for row in em.rows:
        cells = [row.finding]
        for h_id in h_ids:
            rating = row.ratings.get(h_id, "?")
            cells.append(rating if isinstance(rating, str) else rating.value)
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("#### Posterior Updates")
    lines.append("")
    for p in em.posteriors:
        delta = p.posterior - p.prior
        lines.append(
            f"- **{p.hypothesis_id}:** {p.prior:.2f} → {p.posterior:.2f} "
            f"({delta:+.2f}) — {p.reasoning}"
        )

    return "\n".join(lines)


def render_reflexive_review(rr: ReflexiveReview) -> str:
    lines = [
        "### Reflexive Review",
        "",
        f"- **K₀ comparison:** {rr.k0_comparison}",
        f"- **Most surprising finding:** {rr.most_surprising_finding}",
        f"- **Paradigm sensitivity:** {rr.paradigm_sensitivity}",
        f"- **Genuine update:** {'Yes' if rr.genuine_update else 'No'}",
        "",
        "#### Red Team Argument",
        "",
        rr.red_team_argument,
    ]
    return "\n".join(lines)


def render_synthesis(s: Synthesis) -> str:
    lines = [
        "### Synthesis",
        "",
        f"- **Assessment:** {_assessment_display(s.assessment.value)}",
        f"- **Confidence:** {s.confidence.value}",
        f"- **Key imbalances:** {', '.join(s.key_imbalances)}",
        f"- **Paradigm note:** {s.paradigm_note}",
        f"- **K₀ revision:** {s.k0_revision}",
        "- **Disconfirming evidence:**",
    ]
    for e in s.disconfirming_evidence:
        lines.append(f"  - {e}")
    lines.append("")
    lines.append("#### Candidate Moves")
    lines.append("")
    for cm in s.candidate_moves:
        lines.append(f"- **{cm.move}:** {cm.rationale}")
    return "\n".join(lines)


def render_discomfort_heuristic(dh: DiscomfortHeuristic) -> str:
    lines = [
        "### Discomfort Heuristic",
        "",
        f"- **Feels comfortable:** {'Yes' if dh.feels_comfortable else 'No'}",
        f"- **Confidence drop moment:** {dh.confidence_drop_moment}",
        f"- **More uncertain than start:** {'Yes' if dh.more_uncertain_than_start else 'No'}",
    ]
    if dh.warning:
        lines.append(f"- **⚠ Warning:** {dh.warning}")
    return "\n".join(lines)


# ── Full render ──────────────────────────────────────────────────────────────

def render_full(phases_dir: Path, position_data: dict | None = None) -> str:
    """Render all 9 phases to a complete markdown document."""
    phases_dir = Path(phases_dir)
    sections = []

    # Header
    header = "## Deep Analysis — BFIH Protocol"
    if position_data and "fen" in position_data:
        header += f"\n\n**FEN:** `{position_data['fen']}`"
    sections.append(header)

    # Render each phase
    renderers = [
        (1, render_k0), (2, render_hypotheses), (3, render_ontological_scan),
        (4, render_ancestral_check), (5, render_paradigm_inversion),
        (6, render_evidence_matrix), (7, render_reflexive_review),
        (8, render_synthesis), (9, render_discomfort_heuristic),
    ]

    for phase_num, renderer in renderers:
        try:
            model = _load_phase(phases_dir, phase_num)
            sections.append(renderer(model))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            sections.append(f"### Phase {phase_num}\n\n*Error loading: {e}*")

    return "\n\n---\n\n".join(sections) + "\n"


def render_summary(phases_dir: Path) -> str:
    """Render a concise summary from the synthesis phase."""
    phases_dir = Path(phases_dir)

    try:
        synthesis = _load_phase(phases_dir, 8)
    except (FileNotFoundError, json.JSONDecodeError):
        return "Summary unavailable: synthesis phase not found."

    assessment = _assessment_display(synthesis.assessment.value)
    confidence = synthesis.confidence.value
    imbalances = ", ".join(synthesis.key_imbalances)
    moves = ", ".join(cm.move for cm in synthesis.candidate_moves[:3])

    lines = [
        f"**{assessment}** (confidence: {confidence})",
        f"Key: {imbalances}",
        f"K₀ revision: {synthesis.k0_revision}",
        f"Candidate moves: {moves}",
    ]

    # Add discomfort warning if present
    try:
        dh = _load_phase(phases_dir, 9)
        if dh.warning:
            lines.append(f"⚠ {dh.warning}")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Render validated BFIH phase JSON to markdown."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # render
    rp = subparsers.add_parser("render", help="Full markdown render")
    rp.add_argument("dir", help="Directory containing phase_N.json files")
    rp.add_argument("--position-data", help="Path to position data JSON")
    rp.add_argument("--output", help="Output file path (default: stdout)")

    # summary
    sp = subparsers.add_parser("summary", help="Concise summary")
    sp.add_argument("dir", help="Directory containing phase_N.json files")

    args = parser.parse_args()

    if args.command == "render":
        position_data = None
        if args.position_data:
            position_data = json.loads(Path(args.position_data).read_text())

        md = render_full(Path(args.dir), position_data=position_data)

        if args.output:
            Path(args.output).write_text(md)
            print(f"Written to {args.output}")
        else:
            print(md)

    elif args.command == "summary":
        print(render_summary(Path(args.dir)))


if __name__ == "__main__":
    main()
