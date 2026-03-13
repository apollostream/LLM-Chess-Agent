#!/usr/bin/env python3
"""Game Narrative pipeline — critical moment detection, models, and rendering.

Analyzes a full game to identify turning points and generate a connected
narrative that tells the story of how the game was won or lost.

Usage:
    from game_narrative import detect_critical_moments, GameNarrative, render_game_story

    moments = detect_critical_moments("game.pgn", depth=18, threshold_cp=50)
    narrative = GameNarrative(...)  # Claude fills this after reviewing moments
    story_md = render_game_story(narrative)
"""

import io
import math
from enum import StrEnum
from pathlib import Path
from typing import Optional

import chess
import chess.pgn
import chess.svg
from pydantic import BaseModel, Field, model_validator

from engine_eval import EngineEval, _classify_cp_loss, _score_display


def eval_decay(eval_cp: int, scale: int | None) -> float:
    """Compute exponential decay factor based on position eval.

    Returns a value in (0, 1] that scales down the effective significance
    of an eval swing when the position is already lopsided.

    decay = exp(-|eval_cp| / scale)

    At eval=0 the decay is 1.0 (no dampening).  As |eval| grows, the
    decay shrinks, so the effective threshold (threshold_cp / decay)
    increases — requiring a larger swing to register as critical.

    Args:
        eval_cp: Engine evaluation in centipawns before the move.
        scale: Decay constant A_cp.  Larger values = gentler decay.
               None disables decay (returns 1.0).
    """
    if scale is None:
        return 1.0
    return math.exp(-abs(eval_cp) / scale)


# ── Enums ────────────────────────────────────────────────────────────────────

class ArcType(StrEnum):
    gradual_collapse = "gradual_collapse"
    single_blunder = "single_blunder"
    back_and_forth = "back_and_forth"
    missed_opportunity = "missed_opportunity"
    steady_conversion = "steady_conversion"


class Side(StrEnum):
    white = "white"
    black = "black"


# ── Models ───────────────────────────────────────────────────────────────────

class CriticalMoment(BaseModel):
    """A single turning point in the game."""
    move_number: int = Field(ge=1)
    side: Side
    san: str
    fen_before: str
    fen_after: str
    eval_before_cp: int
    eval_after_cp: int
    delta_cp: int
    classification: str = Field(pattern=r"^(best|excellent|good|inaccuracy|mistake|blunder)$")
    engine_best_move: Optional[str] = None
    key_lesson: Optional[str] = None


class StoryPosition(BaseModel):
    """Board position to illustrate a story paragraph."""
    move_number: int = Field(ge=1)
    side: Side
    label: Optional[str] = None  # e.g. "After 22...Ke7" — auto-generated if omitted


class GameNarrative(BaseModel):
    """Complete game narrative synthesized from critical moments."""
    game_metadata: dict
    critical_moments: list[CriticalMoment] = Field(min_length=1)
    arc_type: ArcType
    game_story: str = Field(min_length=80)
    key_lessons: list[str] = Field(min_length=1, max_length=7)
    turning_point_move: int = Field(ge=1)
    turning_point_side: Side
    story_positions: Optional[list[StoryPosition]] = None


# ── Critical Moment Detection ────────────────────────────────────────────────

def detect_critical_moments(
    pgn_path: str | Path,
    depth: int = 18,
    threshold_cp: int = 50,
    decay_scale_cp: int | None = 750,
) -> list[CriticalMoment]:
    """Sweep a game move-by-move with Stockfish and flag eval swings.

    Args:
        pgn_path: Path to PGN file.
        depth: Engine search depth per position.
        threshold_cp: Minimum |delta| in centipawns to flag as critical.
        decay_scale_cp: Exponential decay constant (A_cp).  Raises the
            effective threshold when the position is already lopsided,
            suppressing noise in decided games.  Set to None to disable.
            Default 750: gentle decay that still flags important conversion
            errors while filtering trivial swings in decided positions.

    Returns:
        List of CriticalMoment objects, sorted by move number.
    """
    pgn_path = Path(pgn_path)
    with open(pgn_path) as f:
        game = chess.pgn.read_game(f)

    if game is None:
        return []

    board = game.board()
    moves = list(game.mainline_moves())
    moments = []

    with EngineEval() as engine:
        if not engine.available:
            return []

        # Evaluate starting position
        prev_result = engine.evaluate_position(board, depth=depth)
        if prev_result is None:
            return []
        prev_cp = prev_result.get("score_cp", 0) or 0

        for i, move in enumerate(moves):
            fen_before = board.fen()
            san = board.san(move)
            move_number = (i // 2) + 1
            side = "white" if i % 2 == 0 else "black"

            # Get best move before pushing
            best_move = prev_result.get("best_move") if prev_result else None

            board.push(move)
            fen_after = board.fen()

            result = engine.evaluate_position(board, depth=depth)
            if result is None:
                continue

            curr_cp = result.get("score_cp")
            if curr_cp is None:
                # Mate score — treat as large swing
                mate = result.get("mate_in")
                if mate is not None:
                    curr_cp = 10000 if mate > 0 else -10000
                else:
                    continue

            delta = curr_cp - prev_cp

            # For White's moves, a negative delta is bad for White
            # For Black's moves, a positive delta is bad for Black
            # We want the magnitude of the swing
            abs_delta = abs(delta)

            # Apply eval-based decay: in lopsided positions, require a
            # proportionally larger swing to count as critical.
            decay = eval_decay(prev_cp, decay_scale_cp)
            effective_threshold = threshold_cp / decay if decay > 0 else threshold_cp

            if abs_delta >= effective_threshold:
                # Classify based on centipawn loss from the moving side's perspective
                if side == "white":
                    cp_loss = max(0, -delta)  # White wants positive delta
                else:
                    cp_loss = max(0, delta)   # Black wants negative delta

                classification = _classify_cp_loss(cp_loss)

                moments.append(CriticalMoment(
                    move_number=move_number,
                    side=side,
                    san=san,
                    fen_before=fen_before,
                    fen_after=fen_after,
                    eval_before_cp=prev_cp,
                    eval_after_cp=curr_cp,
                    delta_cp=delta,
                    classification=classification,
                    engine_best_move=best_move,
                ))

            prev_cp = curr_cp
            prev_result = result

    return sorted(moments, key=lambda m: (m.move_number, 0 if m.side == "white" else 1))


# ── Board Diagram Generation ────────────────────────────────────────────────

def replay_to_position(pgn_text: str, move_number: int, side: str) -> tuple[str, str]:
    """Replay a PGN to a specific move and return (FEN, SAN label).

    Args:
        pgn_text: PGN game text.
        move_number: 1-based move number.
        side: "white" or "black" — whose move just completed.

    Returns:
        (fen, label) where label is e.g. "22...Ke7".
    """
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Invalid PGN")

    board = game.board()
    moves = list(game.mainline_moves())

    # Half-move index: move 1 white = 0, move 1 black = 1, move 2 white = 2, etc.
    target_half = (move_number - 1) * 2 + (1 if side == "black" else 0)
    if target_half >= len(moves):
        target_half = len(moves) - 1

    san = ""
    for i, move in enumerate(moves):
        san = board.san(move)
        board.push(move)
        if i == target_half:
            break

    dots = "..." if side == "black" else "."
    label = f"{move_number}{dots}{san}"
    return board.fen(), label


def generate_narrative_boards(
    pgn_text: str,
    story_positions: list["StoryPosition"],
    output_dir: Path,
    base_name: str = "narrative",
) -> list[Path]:
    """Generate SVG board diagrams for each story position.

    Args:
        pgn_text: Full PGN text of the game.
        story_positions: Positions to illustrate.
        output_dir: Directory to write SVG files.
        base_name: Prefix for SVG filenames.

    Returns:
        List of SVG file paths, one per story_position.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    for i, pos in enumerate(story_positions):
        fen, auto_label = replay_to_position(pgn_text, pos.move_number, pos.side)
        if pos.label is None:
            pos.label = f"After {auto_label}"

        board = chess.Board(fen)
        svg_content = chess.svg.board(board, size=400)

        svg_name = f"{base_name}_move{pos.move_number}{pos.side[0]}.svg"
        svg_path = output_dir / svg_name
        svg_path.write_text(svg_content)
        paths.append(svg_path)

    return paths


# ── Rendering ────────────────────────────────────────────────────────────────

def render_game_story(narrative: GameNarrative,
                      output_path: Path | None = None,
                      pgn_text: str | None = None) -> str:
    """Render a GameNarrative to markdown, optionally with board diagrams.

    Args:
        narrative: The completed GameNarrative model.
        output_path: If provided, write the markdown to this file.
        pgn_text: If provided along with story_positions, generates SVG board
            diagrams and embeds them after each story paragraph.

    Returns:
        The rendered markdown string.
    """
    meta = narrative.game_metadata
    sections = []

    # ── Title ────────────────────────────────────────────────────────────
    white = meta.get("white", "White")
    black = meta.get("black", "Black")
    result = meta.get("result", "*")
    date = meta.get("date", "")
    opening = meta.get("opening", "")

    title_lines = [
        f"# Game Story: {white} vs {black}",
        "",
        f"**Result:** {result}",
    ]
    if date:
        title_lines.append(f"**Date:** {date}")
    if opening:
        eco = meta.get("eco", "")
        title_lines.append(f"**Opening:** {opening}" + (f" ({eco})" if eco else ""))

    arc_display = narrative.arc_type.value.replace("_", " ").title()
    title_lines.append(f"**Arc:** {arc_display}")
    sections.append("\n".join(title_lines))

    # ── The Story (with optional board diagrams) ─────────────────────────
    board_paths: list[Path] = []
    positions = narrative.story_positions or []

    if pgn_text and positions and output_path:
        output_dir = Path(output_path).parent
        base_name = Path(output_path).stem
        board_paths = generate_narrative_boards(
            pgn_text, positions, output_dir, base_name,
        )

    # Split story into paragraphs (double newline separated)
    paragraphs = [p.strip() for p in narrative.game_story.split("\n\n") if p.strip()]

    story_lines = ["## The Story", ""]

    # First paragraph (intro) gets no board — it's the overview
    if paragraphs:
        story_lines.append(paragraphs[0])

    # Remaining paragraphs get board diagrams interleaved
    body_paragraphs = paragraphs[1:] if len(paragraphs) > 1 else []
    for i, para in enumerate(body_paragraphs):
        story_lines.append("")
        story_lines.append(para)
        if i < len(board_paths):
            svg_name = board_paths[i].name
            label = positions[i].label or f"Position after move {positions[i].move_number}"
            story_lines.append("")
            story_lines.append(f"![{label}]({svg_name})")

    sections.append("\n".join(story_lines))

    # ── Turning Point ────────────────────────────────────────────────────
    tp_side = narrative.turning_point_side.value.title()
    tp_lines = [
        "## Turning Point",
        "",
        f"**Move {narrative.turning_point_move} ({tp_side})** — the moment the advantage shifted decisively.",
    ]

    # Find the turning point in critical moments
    for cm in narrative.critical_moments:
        if cm.move_number == narrative.turning_point_move and cm.side == narrative.turning_point_side:
            tp_lines.append("")
            tp_lines.append(f"- **Played:** {cm.san} ({cm.classification})")
            if cm.engine_best_move:
                tp_lines.append(f"- **Best was:** {cm.engine_best_move}")
            tp_lines.append(f"- **Eval shift:** {cm.eval_before_cp/100:+.2f} → {cm.eval_after_cp/100:+.2f} (Δ{cm.delta_cp/100:+.2f})")
            if cm.key_lesson:
                tp_lines.append(f"- **Lesson:** {cm.key_lesson}")
            break

    sections.append("\n".join(tp_lines))

    # ── Critical Moments Timeline ────────────────────────────────────────
    timeline_lines = [
        "## Critical Moments",
        "",
        "| Move | Side | Played | Class | Eval Before | Eval After | Δ |",
        "| ---:|:---:|:---:|:---:| ---:| ---:| ---:|",
    ]

    for cm in narrative.critical_moments:
        side_icon = "♔" if cm.side == "white" else "♚"
        timeline_lines.append(
            f"| {cm.move_number} | {side_icon} | {cm.san} | {cm.classification} "
            f"| {cm.eval_before_cp/100:+.2f} | {cm.eval_after_cp/100:+.2f} "
            f"| {cm.delta_cp/100:+.2f} |"
        )

    sections.append("\n".join(timeline_lines))

    # ── Key Lessons ──────────────────────────────────────────────────────
    lesson_lines = [
        "## Key Lessons",
        "",
    ]
    for i, lesson in enumerate(narrative.key_lessons, 1):
        lesson_lines.append(f"{i}. {lesson}")

    sections.append("\n".join(lesson_lines))

    md = "\n\n---\n\n".join(sections) + "\n"

    if output_path:
        output_path = Path(output_path)
        output_path.write_text(md)

    return md
