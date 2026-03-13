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

import chess
import chess.svg

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
        lines.append("")
        lines.append(f"- {h.description}")
        lines.append(f"- *Plan:* {h.plan}")
        lines.append("")
    return "\n".join(lines)


def render_ontological_scan(scan: OntologicalScan) -> str:
    lines = ["### Ontological Scan — 10 Imbalances", ""]
    for f in sorted(scan.findings, key=lambda x: x.number):
        lines.append(
            f"**{f.number}. {f.name}** "
            f"[{f.relevance.value}] [{f.direction.value}]"
        )
        lines.append("")
        lines.append(f"- {f.finding}")
        if f.interaction:
            lines.append(f"- *Interaction:* {f.interaction}")
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
    # Left-align Finding column, center-align hypothesis columns (compact)
    data_seps = "|".join(":---:" for _ in header_cells[1:])
    lines.append(f"| --- |{data_seps}|")

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
        score_part = ""
        if cm.engine_score is not None:
            score_part = f" `[{cm.engine_score}]`"
            if cm.engine_rank is not None:
                score_part = f" `[{cm.engine_score}, #{cm.engine_rank}]`"
        lines.append(f"- **{cm.move}:**{score_part} {cm.rationale}")
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


# ── Engine eval section ──────────────────────────────────────────────────────

def render_engine_eval(position_data: dict) -> str | None:
    """Render engine evaluation summary from position data. Returns None if unavailable."""
    eng = position_data.get("engine", {})
    if not eng.get("available") or not eng.get("eval"):
        return None

    ev = eng["eval"]
    lines = [
        "### Engine Evaluation",
        "",
        f"- **Score:** {ev['score_display']}",
    ]
    if ev.get("mate_in") is not None:
        lines[-1] += f" (mate in {abs(ev['mate_in'])})"
    if ev.get("wdl"):
        w, d, l = ev["wdl"]["win"], ev["wdl"]["draw"], ev["wdl"]["loss"]
        lines.append(f"- **WDL:** {w/10:.1f}% / {d/10:.1f}% / {l/10:.1f}%")
    lines.append(f"- **Best move:** {ev.get('best_move', '?')}")
    if ev.get("pv"):
        lines.append(f"- **PV:** {' '.join(ev['pv'][:8])}")

    top = eng.get("top_lines")
    if top and len(top) > 1:
        lines.append(f"- **Top {len(top)} lines:**")
        for i, line in enumerate(top, 1):
            pv_str = " ".join(line.get("pv", [])[:6])
            lines.append(f"  {i}. ({line['score_display']}) {pv_str}")

    depth = eng.get("depth")
    if depth:
        lines.append(f"- **Depth:** {depth}")

    return "\n".join(lines)


# ── Board diagram ───────────────────────────────────────────────────────────

def generate_board_svg(fen: str, output_path: Path) -> Path:
    """Generate an SVG board diagram from a FEN string.

    Returns the path to the generated SVG file.
    """
    board = chess.Board(fen)
    svg_content = chess.svg.board(board, size=400)
    output_path = Path(output_path)
    output_path.write_text(svg_content)
    return output_path


# ── Full render ──────────────────────────────────────────────────────────────

def render_full(phases_dir: Path, position_data: dict | None = None,
                output_path: Path | None = None) -> str:
    """Render all 9 phases to a complete markdown document.

    If output_path is provided and position_data contains a FEN, generates
    an SVG board diagram alongside the output file.
    """
    phases_dir = Path(phases_dir)
    sections = []

    # Header with optional board diagram
    header = "## Deep Analysis — BFIH Protocol"
    if position_data and "fen" in position_data:
        header += f"\n\n**FEN:** `{position_data['fen']}`"
        if output_path:
            output_path = Path(output_path)
            svg_name = output_path.stem + "_board.svg"
            svg_path = output_path.parent / svg_name
            generate_board_svg(position_data["fen"], svg_path)
            header += f"\n\n![Board Position]({svg_name})"
    sections.append(header)

    # Engine evaluation (if available)
    if position_data:
        engine_section = render_engine_eval(position_data)
        if engine_section:
            sections.append(engine_section)

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


def render_players_guide(phases_dir: Path, position_data: dict | None = None,
                         output_path: Path | None = None) -> str:
    """Render a standalone Player's Guide — coach-style narrative.

    Draws from phases 1 (K0), 3 (Ontological Scan), 8 (Synthesis), and
    9 (Discomfort Heuristic) to produce a concise, actionable document.
    """
    phases_dir = Path(phases_dir)
    sections = []

    # ── Header ──────────────────────────────────────────────────────────
    try:
        synthesis = _load_phase(phases_dir, 8)
    except (FileNotFoundError, json.JSONDecodeError):
        return "Player's Guide unavailable: synthesis phase not found."

    assessment = _assessment_display(synthesis.assessment.value)
    confidence = synthesis.confidence.value

    header = f"# Player's Guide — {assessment}"
    header += f"\n\n**Confidence:** {confidence}"

    if position_data and "fen" in position_data:
        header += f"\n\n**FEN:** `{position_data['fen']}`"
        if output_path:
            output_path = Path(output_path)
            svg_name = output_path.stem + "_board.svg"
            svg_path = output_path.parent / svg_name
            generate_board_svg(position_data["fen"], svg_path)
            header += f"\n\n![Board Position]({svg_name})"

    sections.append(header)

    # ── Engine confirmation (brief) ─────────────────────────────────────
    if position_data:
        eng = position_data.get("engine", {})
        if eng.get("available") and eng.get("eval"):
            ev = eng["eval"]
            engine_line = f"*Engine confirms: {ev['score_display']}"
            if ev.get("best_move"):
                engine_line += f", best move {ev['best_move']}"
            if eng.get("depth"):
                engine_line += f" (depth {eng['depth']})"
            engine_line += "*"
            sections.append(engine_line)

    # ── What You Should See ─────────────────────────────────────────────
    see_lines = ["## What You Should See", ""]
    try:
        scan = _load_phase(phases_dir, 3)
        # Prefer high-relevance findings; fall back to all if none are high
        high = [f for f in scan.findings if f.relevance.value == "high"]
        findings = high if high else sorted(
            scan.findings, key=lambda x: x.number,
        )[:4]
        for f in sorted(findings, key=lambda x: x.number):
            see_lines.append(
                f"- **{f.name}** [{f.direction.value}] — {f.finding}"
            )
    except (FileNotFoundError, json.JSONDecodeError):
        see_lines.append("- *(Ontological scan unavailable)*")

    sections.append("\n".join(see_lines))

    # ── The Story of This Position ──────────────────────────────────────
    story_lines = ["## The Story of This Position", ""]

    try:
        k0 = _load_phase(phases_dir, 1)
        story_lines.append(f"*{k0.opening_context}*")
        story_lines.append("")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    story_lines.append(synthesis.position_narrative)
    sections.append("\n".join(story_lines))

    # ── Your Plan ───────────────────────────────────────────────────────
    plan_lines = ["## Your Plan", ""]
    for cm in synthesis.candidate_moves:
        score_part = ""
        if cm.engine_score is not None:
            score_part = f" `[{cm.engine_score}]`"
            if cm.engine_rank is not None:
                score_part = f" `[{cm.engine_score}, #{cm.engine_rank}]`"
        plan_lines.append(f"- **{cm.move}**{score_part} — {cm.rationale}")
    sections.append("\n".join(plan_lines))

    # ── Key Takeaway ────────────────────────────────────────────────────
    takeaway_lines = [
        "## Key Takeaway",
        "",
        synthesis.key_takeaway,
    ]

    # Surface discomfort warning if present
    try:
        dh = _load_phase(phases_dir, 9)
        if dh.warning:
            takeaway_lines.append("")
            takeaway_lines.append(f"⚠ *{dh.warning}*")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    sections.append("\n".join(takeaway_lines))

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

    # guide
    gp = subparsers.add_parser("guide", help="Player's Guide (coach-style)")
    gp.add_argument("dir", help="Directory containing phase_N.json files")
    gp.add_argument("--position-data", help="Path to position data JSON")
    gp.add_argument("--output", help="Output file path (default: stdout)")

    # summary
    sp = subparsers.add_parser("summary", help="Concise summary")
    sp.add_argument("dir", help="Directory containing phase_N.json files")

    args = parser.parse_args()

    if args.command == "guide":
        position_data = None
        if args.position_data:
            position_data = json.loads(Path(args.position_data).read_text())

        output_path = Path(args.output) if args.output else None
        md = render_players_guide(Path(args.dir), position_data=position_data,
                                  output_path=output_path)

        if output_path:
            Path(output_path).write_text(md)
            print(f"Written to {args.output}")
        else:
            print(md)

    elif args.command == "render":
        position_data = None
        if args.position_data:
            position_data = json.loads(Path(args.position_data).read_text())

        output_path = Path(args.output) if args.output else None
        md = render_full(Path(args.dir), position_data=position_data,
                         output_path=output_path)

        if output_path:
            output_path.write_text(md)
            print(f"Written to {args.output}")
        else:
            print(md)

    elif args.command == "summary":
        print(render_summary(Path(args.dir)))


if __name__ == "__main__":
    main()
