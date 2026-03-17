#!/usr/bin/env python3
"""Batch-process PGN files into game cache for feature extraction.

Evaluates all positions in each PGN with Stockfish and caches results
to analysis/game_cache/ — same format the web app uses.

Supports both single-game and multi-game PGN files. Each game in a
multi-game file is cached independently (separate hash, separate JSON).

Usage:
    # Process all PGN files in ~/Documents/Chess/
    python batch_cache_games.py ~/Documents/Chess/*.pgn

    # Process a multi-game PGN (e.g., sampled tournament games)
    python batch_cache_games.py analysis/sampled/tier1/tier1_sampled.pgn

    # Process with custom depth
    python batch_cache_games.py --depth 14 --lines 3 game1.pgn game2.pgn

    # Skip already-cached games
    python batch_cache_games.py ~/Documents/Chess/*.pgn  # (auto-skips cached)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
from pathlib import Path

import chess
import chess.pgn

# Add scripts to path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from engine_eval import EngineEval
from game_narrative import detect_critical_moments_from_cache

ANALYSIS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "analysis"
CACHE_DIR = ANALYSIS_DIR / "game_cache"


def pgn_hash(pgn: str) -> str:
    """Deterministic hash of PGN text (matches game_store.pgn_hash)."""
    normalized = pgn.strip().replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode()).hexdigest()


def extract_fens(pgn_text: str) -> list[str]:
    """Parse PGN and return all FENs from start to end position."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return []
    board = game.board()
    fens = [board.fen()]
    for move in game.mainline_moves():
        board.push(move)
        fens.append(board.fen())
    return fens


def extract_fens_from_game(game: chess.pgn.Game) -> list[str]:
    """Extract FENs from a parsed Game object."""
    board = game.board()
    fens = [board.fen()]
    for move in game.mainline_moves():
        board.push(move)
        fens.append(board.fen())
    return fens


def game_to_pgn_text(game: chess.pgn.Game) -> str:
    """Export a Game object to PGN text (without engine comments)."""
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    return game.accept(exporter)


def evaluate_all(engine: EngineEval, fens: list[str], depth: int, lines: int) -> dict[str, dict]:
    """Evaluate all positions in a single engine session."""
    results: dict[str, dict] = {}
    for i, fen in enumerate(fens):
        if fen in results:
            print(f"\r  Position {i + 1}/{len(fens)} (cached)", end="", flush=True)
            continue

        board = chess.Board(fen)
        multi = engine.evaluate_multipv(board, num_lines=lines, depth=depth)
        single = multi[0] if multi and len(multi) > 0 else None

        results[fen] = {"available": True, "eval": single, "top_lines": multi}
        print(f"\r  Position {i + 1}/{len(fens)}", end="", flush=True)

    print()
    return results


def select_top_moments(moments: list[dict], n: int = 5) -> list[dict]:
    """Auto-select top N moments by eval swing magnitude."""
    sorted_moments = sorted(moments, key=lambda m: abs(m.get("delta_cp", 0)), reverse=True)
    selected = sorted_moments[:n]
    return sorted(selected, key=lambda m: (m.get("move_number", 0), 0 if m.get("side") == "white" else 1))


def process_game(
    game: chess.pgn.Game,
    pgn_text: str,
    depth: int,
    lines: int,
    engine: EngineEval,
    label: str = "",
) -> bool:
    """Process a single game. Returns True if processed, False if skipped."""
    h = pgn_hash(pgn_text)
    short_id = h[:12]

    # Check if already cached
    cache_file = CACHE_DIR / f"{short_id}.json"
    if cache_file.exists():
        print(f"  SKIP (cached): {label or short_id}")
        return False

    fens = extract_fens_from_game(game)
    if not fens or len(fens) < 2:
        print(f"  SKIP (no moves): {label or short_id}")
        return False

    print(f"  Evaluating {len(fens)} positions at depth {depth}...")
    t0 = time.time()
    engine_evals = evaluate_all(engine, fens, depth, lines)
    eval_time = time.time() - t0

    print(f"  Detecting critical moments...")
    moments_objs = detect_critical_moments_from_cache(pgn_text, engine_evals)
    moments_all = [m.model_dump() for m in moments_objs]
    moments_selected = select_top_moments(moments_all, n=5)

    # Save cache
    store = {
        "pgn": pgn_text,
        "pgn_hash": h,
        "positions": fens,
        "depth": depth,
        "lines": lines,
        "engine_evals": engine_evals,
        "critical_moments_all": moments_all,
        "critical_moments_selected": moments_selected,
        "synopsis_text": None,
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(store, f)

    size_kb = cache_file.stat().st_size / 1024
    print(f"  Done: {len(fens)} positions, {len(moments_all)} moments, {eval_time:.1f}s, {size_kb:.0f}KB")
    return True


def process_pgn_file(
    pgn_path: Path, depth: int, lines: int, engine: EngineEval
) -> tuple[int, int]:
    """Process all games in a PGN file. Returns (processed, total) counts."""
    processed = 0
    total = 0

    with open(pgn_path, encoding="utf-8", errors="replace") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            total += 1

            # Get individual game PGN text
            pgn_text = game_to_pgn_text(game)
            white = game.headers.get("White", "?")
            black = game.headers.get("Black", "?")
            label = f"#{total} {white} vs {black}"

            if process_game(game, pgn_text, depth, lines, engine, label):
                processed += 1

    return processed, total


def main():
    parser = argparse.ArgumentParser(description="Batch-process PGN files into game cache")
    parser.add_argument("pgn_files", nargs="+", help="PGN files to process")
    parser.add_argument("--depth", type=int, default=12, help="Stockfish depth (default: 12)")
    parser.add_argument("--lines", type=int, default=3, help="Multi-PV lines (default: 3)")
    parser.add_argument("--threads", type=int, default=2, help="Stockfish threads (default: 2)")
    parser.add_argument("--hash-mb", type=int, default=256, help="Stockfish hash MB (default: 256)")
    args = parser.parse_args()

    pgn_paths = [Path(p) for p in args.pgn_files]
    valid = [p for p in pgn_paths if p.exists() and p.suffix == ".pgn"]

    if not valid:
        print("No valid PGN files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Processing {len(valid)} PGN files (depth={args.depth}, lines={args.lines})")
    print(f"Cache directory: {CACHE_DIR}\n")

    t_total = time.time()
    total_processed = 0
    total_games = 0

    with EngineEval(threads=args.threads, hash_mb=args.hash_mb) as engine:
        if not engine.available:
            print("ERROR: Stockfish not available", file=sys.stderr)
            sys.exit(1)

        for pgn_path in valid:
            print(f"\n[{pgn_path.name}]")
            processed, total = process_pgn_file(pgn_path, args.depth, args.lines, engine)
            total_processed += processed
            total_games += total
            if total > 1:
                print(f"  File subtotal: {processed}/{total} games processed")

    elapsed = time.time() - t_total
    print(f"\n{'=' * 50}")
    print(f"Processed {total_processed}/{total_games} games in {elapsed:.1f}s")
    print(f"Cache: {CACHE_DIR}")


if __name__ == "__main__":
    main()
