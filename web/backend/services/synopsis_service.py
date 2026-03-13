"""Game Synopsis pipeline — engine eval → Player's Guides → synthesis.

Orchestrates three phases:
1. Engine + Analysis (parallel) for each critical moment
2. Player's Guides (sequential, cached) for each moment
3. Synthesis (streaming) — all guides into one coherent narrative
"""

from __future__ import annotations

import asyncio
import io
import json
import re
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import chess
import chess.pgn
import chess.svg

from config import PROJECT_ROOT
from services.agent_service import stream_agent, _sse
from services.cache import agent_cache, analysis_cache, engine_cache
from services import chess_pipeline

ANALYSIS_DIR = PROJECT_ROOT / "analysis"


async def stream_synopsis(
    moments: list[dict],
    pgn: str,
    depth: int = 20,
    lines: int = 3,
) -> AsyncIterator[str]:
    """Run the full synopsis pipeline, yielding SSE events throughout."""
    n = len(moments)

    # --- Phase 1: Engine + Analysis (parallel) ---
    sem = asyncio.Semaphore(2)  # limit Stockfish concurrency
    analysis_results: dict[str, dict] = {}
    engine_results: dict[str, dict] = {}

    async def _fetch_position(i: int, fen: str) -> None:
        async with sem:
            # Check analysis cache
            cached_analysis = analysis_cache.get(fen, "engine")
            if cached_analysis is not None:
                analysis_results[fen] = cached_analysis
            else:
                result = await asyncio.to_thread(
                    chess_pipeline.analyze_position, fen, True, depth, lines
                )
                analysis_cache.put(fen, "engine", value=result)
                analysis_results[fen] = result

            # Check engine cache
            cached_engine = engine_cache.get(fen, str(depth), str(lines))
            if cached_engine is not None:
                engine_results[fen] = cached_engine
            else:
                result = await asyncio.to_thread(
                    chess_pipeline.evaluate_position, fen, depth, lines
                )
                if result:
                    engine_cache.put(fen, str(depth), str(lines), value=result)
                    engine_results[fen] = result

    tasks = []
    for i, m in enumerate(moments):
        fen = m["fen_before"]
        tasks.append(_fetch_position(i, fen))

    # Run all engine/analysis tasks, yielding progress after each completes
    completed = 0
    for coro in asyncio.as_completed(tasks):
        await coro
        completed += 1
        yield _sse({"type": "progress", "phase": "engine", "current": completed, "total": n})

    # --- Phase 2: Player's Guides (sequential, cached) ---
    guides: list[str] = []
    for i, m in enumerate(moments):
        fen = m["fen_before"]
        cache_key = ("guide", fen, str(depth), str(lines))
        cached_guide = agent_cache.get(*cache_key)

        if cached_guide is not None:
            guides.append(cached_guide)
        else:
            # Stream the guide, accumulate text, cache it
            guide_parts: list[str] = []
            async for chunk in stream_agent(
                mode="guide",
                fen=fen,
                analysis_json=json.dumps(analysis_results.get(fen, {})),
                engine_json=json.dumps(engine_results.get(fen, {})),
                depth=depth,
                lines=lines,
            ):
                if chunk.startswith("data: "):
                    try:
                        event = json.loads(chunk[6:].rstrip("\n"))
                        if event.get("type") == "text":
                            guide_parts.append(event["content"])
                    except json.JSONDecodeError:
                        guide_parts.append(chunk[6:].rstrip("\n"))

            guide_text = "".join(guide_parts)
            agent_cache.put(*cache_key, value=guide_text)
            guides.append(guide_text)

        yield _sse({
            "type": "progress", "phase": "guide",
            "current": i + 1, "total": n,
        })

    # --- Phase 3: Synthesis (streaming to user) ---
    yield _sse({"type": "progress", "phase": "synthesis", "current": 0, "total": 1})

    # Build guides block
    guide_sections = []
    for m, guide_text in zip(moments, guides):
        fen = m["fen_before"]
        # Extract engine's top move for unambiguous reference
        engine_best = ""
        eng = engine_results.get(fen)
        if eng and eng.get("top_lines"):
            top = eng["top_lines"][0]
            best_move = top.get("best_move", "")
            score = top.get("score_display", "")
            if best_move:
                engine_best = f"\nEngine best move: {best_move} ({score})"

        section = (
            f"### Move {m['move_number']} ({m['side']}): {m['san']} "
            f"({m.get('classification', 'unknown')}, Δ{m.get('delta_cp', 0)}cp)\n"
            f"FEN: {fen}{engine_best}\n\n"
            f"{guide_text}\n\n---"
        )
        guide_sections.append(section)

    guides_block = "\n\n".join(guide_sections)

    async for chunk in stream_agent(
        mode="synthesis",
        pgn=pgn,
        guides_block=guides_block,
        n_moments=n,
    ):
        yield chunk


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:40].rstrip("-")


def _extract_players(pgn: str) -> tuple[str, str]:
    """Extract White and Black player names from PGN headers."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return ("white", "black")
    white = game.headers.get("White", "white")
    black = game.headers.get("Black", "black")
    return (white, black)


def save_synopsis(
    synopsis_text: str,
    moments: list[dict],
    pgn: str,
) -> Path:
    """Save synopsis markdown and board SVGs to the analysis directory.

    Returns the path to the saved markdown file.
    """
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    white, black = _extract_players(pgn)
    today = date.today().isoformat()
    slug = _slugify(f"{white}-vs-{black}-synopsis")
    base_name = f"{today}_{slug}"

    # Generate board SVGs for each critical moment
    board_refs: list[str] = []
    for m in moments:
        fen = m["fen_before"]
        board = chess.Board(fen)
        svg = chess.svg.board(board, size=400)

        side_char = m["side"][0]
        svg_name = f"{base_name}_move{m['move_number']}{side_char}.svg"
        svg_path = ANALYSIS_DIR / svg_name
        svg_path.write_text(svg)

        dots = "..." if m["side"] == "black" else "."
        label = f"{m['move_number']}{dots}{m['san']}"
        board_refs.append((m["move_number"], m["side"], svg_name, label, m.get("classification", "")))

    # Inject board image references into the synopsis markdown
    lines = synopsis_text.split("\n")
    result_lines: list[str] = []
    pending = list(board_refs)

    for i, line in enumerate(lines):
        result_lines.append(line)
        # At paragraph boundaries, check if this paragraph mentions a pending moment
        next_blank = i + 1 >= len(lines) or lines[i + 1].strip() == ""
        if next_blank and line.strip() and pending:
            for j, (move_num, side, svg_name, label, classification) in enumerate(pending):
                dots_re = r"\.\.\." if side == "black" else r"\."
                pat = re.compile(rf"\b{move_num}{dots_re}|[Mm]ove\s+{move_num}\b")
                if pat.search(line):
                    result_lines.append("")
                    result_lines.append(f"![Before {label} ({classification})]({svg_name})")
                    pending.pop(j)
                    break

    # Append any unmatched boards at the end
    for move_num, side, svg_name, label, classification in pending:
        result_lines.append("")
        result_lines.append(f"![Before {label} ({classification})]({svg_name})")

    final_md = "\n".join(result_lines)

    md_path = ANALYSIS_DIR / f"{base_name}.md"
    md_path.write_text(final_md)

    return md_path
