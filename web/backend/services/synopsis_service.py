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
from services import game_store

ANALYSIS_DIR = PROJECT_ROOT / "analysis"


async def stream_synopsis(
    moments: list[dict],
    pgn: str,
    depth: int = 20,
    lines: int = 3,
) -> AsyncIterator[str]:
    """Run the full synopsis pipeline, yielding SSE events throughout."""
    n = len(moments)

    # --- Phase 1: Engine + Analysis (parallel or from game cache) ---
    analysis_results: dict[str, dict] = {}
    engine_results: dict[str, dict] = {}

    g = game_store.active_game

    if g:
        # Read engine data from game cache — no Stockfish calls needed
        for i, m in enumerate(moments):
            fen = m["fen_before"]
            cached_engine = g.engine_evals.get(fen)
            if cached_engine:
                engine_results[fen] = cached_engine

            # Analysis still needs to be computed (deterministic, no Stockfish)
            cached_analysis = analysis_cache.get(fen, "engine")
            if cached_analysis is not None:
                analysis_results[fen] = cached_analysis
            else:
                result = await asyncio.to_thread(
                    chess_pipeline.analyze_position, fen, False, depth, lines
                )
                # Inject cached engine data into analysis
                if cached_engine:
                    result["engine"] = cached_engine
                analysis_cache.put(fen, "engine", value=result)
                analysis_results[fen] = result

            yield _sse({"type": "progress", "phase": "engine", "current": i + 1, "total": n})
    else:
        # Fallback: original behavior with Stockfish calls
        sem = asyncio.Semaphore(2)

        async def _fetch_position(i: int, fen: str) -> None:
            async with sem:
                cached_analysis = analysis_cache.get(fen, "engine")
                if cached_analysis is not None:
                    analysis_results[fen] = cached_analysis
                else:
                    result = await asyncio.to_thread(
                        chess_pipeline.analyze_position, fen, True, depth, lines
                    )
                    analysis_cache.put(fen, "engine", value=result)
                    analysis_results[fen] = result

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

    # Stream opening moves prefix before Claude's synthesis
    first_move = min(m["move_number"] for m in moments) if moments else 10
    opening_moves = _extract_opening_moves(pgn, first_move - 1)
    if opening_moves:
        prefix = f"> **Opening moves:** {opening_moves}\n\n"
        yield _sse({"type": "opening_moves", "content": prefix})

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
                # Include alternative lines so synthesis can contrast
                for j, alt in enumerate(eng["top_lines"][1:], 2):
                    alt_move = alt.get("best_move", "")
                    alt_score = alt.get("score_display", "")
                    if alt_move:
                        engine_best += f"\nEngine line {j}: {alt_move} ({alt_score})"

        # Strip eval scores from guide text so the synthesis prompt uses
        # the authoritative header values, not hallucinated ones.
        cleaned_guide = re.sub(
            r"[(\[]\s*[+\-−]?\d+\.\d+\s*[)\]]"  # (+1.23) or [+1.23]
            r"|(?<=\s)[+\-−]\d+\.\d+(?=[\s,;.)\"]|$)",  # bare +1.23
            "",
            guide_text,
        )

        section = (
            f"### Move {m['move_number']} ({m['side']}): {m['san']} "
            f"({m.get('classification', 'unknown')}, Δ{m.get('delta_cp', 0)}cp)\n"
            f"FEN: {fen}{engine_best}\n\n"
            f"{cleaned_guide}\n\n---"
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


def build_opening_prefix(pgn: str, moments: list[dict]) -> str:
    """Build the opening moves blockquote to prepend to the synopsis."""
    first_move = min(m["move_number"] for m in moments) if moments else 10
    opening_moves = _extract_opening_moves(pgn, first_move - 1)
    if opening_moves:
        return f"> **Opening moves:** {opening_moves}\n\n"
    return ""


def build_synopsis_appendix(pgn: str) -> str:
    """Build the appendix markdown (final board + PGN) for the app display.

    Board images use API URLs so they render in the browser.
    """
    parts: list[str] = []

    # Final position board
    final_fen = _get_final_position_fen(pgn)
    if final_fen:
        parts.append("\n\n---\n\n### Final Position\n")
        parts.append(_board_img_api(final_fen, "Final position"))

    # Full PGN move list
    full_movelist = _extract_full_movelist(pgn)
    if full_movelist:
        headers = _extract_game_headers(pgn)
        result = headers.get("Result", "*")
        parts.append("\n\n---\n\n### Complete Game\n")
        parts.append(f"\n```\n{full_movelist} {result}\n```")

    return "".join(parts)


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


def _extract_opening_moves(pgn: str, up_to_move: int) -> str:
    """Extract the opening move list from PGN up to the given move number.

    Returns a compact move string like '1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5'.
    """
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return ""

    parts: list[str] = []
    node = game
    while node.variations:
        node = node.variations[0]
        board = node.board()
        move_num = board.fullmove_number
        # node.move is the move that led to this position
        if board.turn == chess.BLACK:
            # White just moved → fullmove_number is the current move
            if move_num > up_to_move:
                break
            san = node.parent.board().san(node.move)
            parts.append(f"{move_num}.{san}")
        else:
            # Black just moved → fullmove_number is next move
            if move_num - 1 > up_to_move:
                break
            san = node.parent.board().san(node.move)
            parts.append(san)

    return " ".join(parts)


def _extract_full_movelist(pgn: str) -> str:
    """Extract the full move list from PGN in standard notation."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return ""

    exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
    return game.accept(exporter).strip()


def _get_final_position_fen(pgn: str) -> str | None:
    """Get the FEN of the final position in the game."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return None
    return game.end().board().fen()


def _extract_game_headers(pgn: str) -> dict[str, str]:
    """Extract key PGN headers."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return {}
    return dict(game.headers)


def _board_img_api(fen: str, label: str, classification: str = "") -> str:
    """Markdown image tag using the board SVG API endpoint."""
    encoded = fen.replace(" ", "%20")
    alt = f"Before {label}"
    if classification:
        alt += f" ({classification})"
    return f"![{alt}](/api/v1/board.svg?fen={encoded}&size=360)"


def _enrich_synopsis(
    synopsis_text: str,
    moments: list[dict],
    pgn: str,
    *,
    img_fn: callable,
    final_img_fn: callable | None = None,
) -> list[str]:
    """Core enrichment logic: insert opening moves, board images, final board, PGN.

    img_fn(moment, label, classification) -> markdown image string
    final_img_fn(fen) -> markdown image string (or None to skip)
    """
    # Determine the first critical moment's move number for opening moves
    first_moment_move = min(m["move_number"] for m in moments) if moments else 10
    opening_moves = _extract_opening_moves(pgn, first_moment_move - 1)

    # Extract game headers for result line
    headers = _extract_game_headers(pgn)
    result = headers.get("Result", "*")

    # Build board refs with labels
    board_refs = []
    for m in moments:
        dots = "..." if m["side"] == "black" else "."
        label = f"{m['move_number']}{dots}{m['san']}"
        board_refs.append((m, label, m.get("classification", "")))

    lines = synopsis_text.split("\n")
    result_lines: list[str] = []
    pending = list(board_refs)
    opening_inserted = False

    for i, line in enumerate(lines):
        # Insert opening moves before the first narrative paragraph
        if (not opening_inserted and line.strip()
                and not line.startswith("#") and not line.startswith("---")
                and not line.startswith("**")):
            if opening_moves:
                result_lines.append(f"> **Opening moves:** {opening_moves}")
                result_lines.append("")
            opening_inserted = True

        result_lines.append(line)
        # At paragraph boundaries, inject board diagram
        next_blank = i + 1 >= len(lines) or lines[i + 1].strip() == ""
        if next_blank and line.strip() and pending:
            for j, (m, label, classification) in enumerate(pending):
                move_num = m["move_number"]
                side = m["side"]
                dots_re = r"\.\.\." if side == "black" else r"\."
                pat = re.compile(rf"\b{move_num}{dots_re}|[Mm]ove\s+{move_num}\b")
                if pat.search(line):
                    result_lines.append("")
                    result_lines.append(img_fn(m, label, classification))
                    pending.pop(j)
                    break

    # Unmatched boards at the end
    for m, label, classification in pending:
        result_lines.append("")
        result_lines.append(img_fn(m, label, classification))

    # Final position board
    final_fen = _get_final_position_fen(pgn)
    if final_fen and final_img_fn:
        result_lines.append("")
        result_lines.append("---")
        result_lines.append("")
        result_lines.append("### Final Position")
        result_lines.append("")
        result_lines.append(final_img_fn(final_fen))

    # Full PGN move list
    full_movelist = _extract_full_movelist(pgn)
    if full_movelist:
        result_lines.append("")
        result_lines.append("---")
        result_lines.append("")
        result_lines.append("### Complete Game")
        result_lines.append("")
        result_lines.append("```")
        result_lines.append(f"{full_movelist} {result}")
        result_lines.append("```")

    return result_lines


def save_synopsis(
    synopsis_text: str,
    moments: list[dict],
    pgn: str,
) -> str:
    """Save synopsis markdown and board SVGs to the analysis directory.

    Adds three programmatic elements:
    1. Opening moves before the first narrative paragraph
    2. Final position board SVG after the synopsis text
    3. Full PGN move list appended at the end

    Returns the enriched markdown for the app (with API image URLs).
    Also saves a disk version (with local SVG file paths).
    """
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    white, black = _extract_players(pgn)
    today = date.today().isoformat()
    slug = _slugify(f"{white}-vs-{black}-synopsis")
    base_name = f"{today}_{slug}"

    # Generate board SVGs for each critical moment and build name map
    svg_names: dict[str, str] = {}  # "move_num+side_char" -> svg filename
    for m in moments:
        fen = m["fen_before"]
        board = chess.Board(fen)
        svg = chess.svg.board(board, size=400)

        side_char = m["side"][0]
        key = f"{m['move_number']}{side_char}"
        svg_name = f"{base_name}_move{key}.svg"
        (ANALYSIS_DIR / svg_name).write_text(svg)
        svg_names[key] = svg_name

    # Generate final position board SVG
    final_fen = _get_final_position_fen(pgn)
    final_svg_name = None
    if final_fen:
        final_board = chess.Board(final_fen)
        final_svg = chess.svg.board(final_board, size=400)
        final_svg_name = f"{base_name}_final.svg"
        (ANALYSIS_DIR / final_svg_name).write_text(final_svg)

    # --- Disk version (local SVG paths) ---
    def disk_img(m: dict, label: str, classification: str) -> str:
        key = f"{m['move_number']}{m['side'][0]}"
        name = svg_names.get(key, "")
        alt = f"Before {label} ({classification})" if classification else f"Before {label}"
        return f"![{alt}]({name})"

    def disk_final_img(fen: str) -> str:
        return f"![Final position]({final_svg_name})" if final_svg_name else ""

    disk_lines = _enrich_synopsis(
        synopsis_text, moments, pgn,
        img_fn=disk_img, final_img_fn=disk_final_img,
    )
    disk_md = "\n".join(disk_lines)
    md_path = ANALYSIS_DIR / f"{base_name}.md"
    md_path.write_text(disk_md)

    # --- App version (API image URLs) ---
    def api_img(m: dict, label: str, classification: str) -> str:
        return _board_img_api(m["fen_before"], label, classification)

    def api_final_img(fen: str) -> str:
        return _board_img_api(fen, "Final position")

    app_lines = _enrich_synopsis(
        synopsis_text, moments, pgn,
        img_fn=api_img, final_img_fn=api_final_img,
    )

    return "\n".join(app_lines)
