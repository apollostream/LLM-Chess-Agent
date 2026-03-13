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

from enum import StrEnum
from pathlib import Path
from typing import Optional

import chess
import chess.pgn
from pydantic import BaseModel, Field, model_validator

from engine_eval import EngineEval, _classify_cp_loss, _score_display


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


class GameNarrative(BaseModel):
    """Complete game narrative synthesized from critical moments."""
    game_metadata: dict
    critical_moments: list[CriticalMoment] = Field(min_length=1)
    arc_type: ArcType
    game_story: str = Field(min_length=80)
    key_lessons: list[str] = Field(min_length=1, max_length=7)
    turning_point_move: int = Field(ge=1)
    turning_point_side: Side


# ── Critical Moment Detection ────────────────────────────────────────────────

def detect_critical_moments(
    pgn_path: str | Path,
    depth: int = 18,
    threshold_cp: int = 50,
) -> list[CriticalMoment]:
    """Sweep a game move-by-move with Stockfish and flag eval swings.

    Args:
        pgn_path: Path to PGN file.
        depth: Engine search depth per position.
        threshold_cp: Minimum |delta| in centipawns to flag as critical.

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

            if abs_delta >= threshold_cp:
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


# ── Rendering ────────────────────────────────────────────────────────────────

def render_game_story(narrative: GameNarrative,
                      output_path: Path | None = None) -> str:
    """Render a GameNarrative to markdown.

    Args:
        narrative: The completed GameNarrative model.
        output_path: If provided, write the markdown to this file.

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

    # ── The Story ────────────────────────────────────────────────────────
    story_lines = [
        "## The Story",
        "",
        narrative.game_story,
    ]
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
