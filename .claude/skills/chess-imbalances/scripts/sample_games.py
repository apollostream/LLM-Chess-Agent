#!/usr/bin/env python3
"""Filter and sample games from downloaded PGN files for the causality dataset.

Reads multi-game PGN files, filters by quality criteria, applies stratified
sampling, and outputs individual PGN files ready for batch_cache_games.py.

Usage:
    # Sample from TCEC superfinals/premier (Tier 1)
    python sample_games.py tier1 analysis/downloads/tier1_engines/tcec/ \
        --output analysis/sampled/tier1/ --max-games 200

    # Sample from GM collections (Tier 2)
    python sample_games.py tier2 analysis/downloads/tier2_gm/ \
        --output analysis/sampled/tier2/ --max-games 200

    # Dry run — just show statistics
    python sample_games.py tier1 analysis/downloads/tier1_engines/tcec/ --dry-run
"""

from __future__ import annotations

import argparse
import io
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

import chess
import chess.pgn


def parse_games(pgn_path: Path, limit: int | None = None) -> list[chess.pgn.Game]:
    """Parse all games from a PGN file."""
    games = []
    with open(pgn_path, encoding="utf-8", errors="replace") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            games.append(game)
            if limit and len(games) >= limit:
                break
    return games


def game_move_count(game: chess.pgn.Game) -> int:
    """Count full moves in a game."""
    return sum(1 for _ in game.mainline_moves())


def get_header(game: chess.pgn.Game, key: str, default: str = "") -> str:
    return game.headers.get(key, default)


def get_elo(game: chess.pgn.Game, color: str) -> int | None:
    """Parse Elo rating from headers. Returns None if unavailable."""
    key = f"{color}Elo"
    val = get_header(game, key)
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def game_to_pgn_text(game: chess.pgn.Game) -> str:
    """Export a Game object back to PGN text."""
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    return game.accept(exporter)


def classify_result(game: chess.pgn.Game) -> str:
    """Classify game result: white_win, black_win, draw, unknown."""
    result = get_header(game, "Result")
    if result == "1-0":
        return "white_win"
    elif result == "0-1":
        return "black_win"
    elif result == "1/2-1/2":
        return "draw"
    return "unknown"


def eco_category(game: chess.pgn.Game) -> str:
    """Extract broad ECO category (A, B, C, D, E) or 'unknown'."""
    eco = get_header(game, "ECO")
    if eco and len(eco) >= 1 and eco[0] in "ABCDE":
        return eco[0]
    return "unknown"


# ─── Tier 1: Engine game filters ─────────────────────────────────────────────

def is_tcec_superfinal(game: chess.pgn.Game) -> bool:
    """Check if game is from a TCEC Superfinal."""
    event = get_header(game, "Event").lower()
    return "superfinal" in event or "sufi" in event


def is_tcec_premier(game: chess.pgn.Game) -> bool:
    """Check if game is from TCEC Premier Division."""
    event = get_header(game, "Event").lower()
    return "premier" in event or "division p" in event


def is_top_engine(game: chess.pgn.Game) -> bool:
    """Check if both players are top engines."""
    top_engines = {
        "stockfish", "lczero", "leela", "lc0", "komodo", "ethereal",
        "igel", "koivisto", "berserk", "seer", "dragon", "torch",
        "rofchade", "slowchess", "clover", "caissa", "obsidian",
        "shashchess", "brainlearn", "stoofvlees",
    }
    white = get_header(game, "White").lower()
    black = get_header(game, "Black").lower()
    return any(e in white for e in top_engines) and any(e in black for e in top_engines)


def filter_tier1(games: list[chess.pgn.Game], min_moves: int = 30) -> list[chess.pgn.Game]:
    """Filter engine games: superfinals + premier division, min moves."""
    filtered = []
    for g in games:
        if game_move_count(g) < min_moves:
            continue
        if is_tcec_superfinal(g) or is_tcec_premier(g):
            filtered.append(g)
    return filtered


# ─── Tier 2: GM game filters ─────────────────────────────────────────────────

def filter_tier2(games: list[chess.pgn.Game], min_moves: int = 30, min_elo: int = 2500) -> list[chess.pgn.Game]:
    """Filter GM games: both players rated min_elo+, min moves, classical/rapid."""
    filtered = []
    for g in games:
        if game_move_count(g) < min_moves:
            continue
        # Check ratings if available
        w_elo = get_elo(g, "White")
        b_elo = get_elo(g, "Black")
        if w_elo is not None and w_elo < min_elo:
            continue
        if b_elo is not None and b_elo < min_elo:
            continue
        # Skip bullet games (time control < 3 minutes)
        tc = get_header(game=g, key="TimeControl")
        if tc:
            match = re.match(r"(\d+)", tc)
            if match and int(match.group(1)) < 180:
                continue
        filtered.append(g)
    return filtered


# ─── Stratified sampling ─────────────────────────────────────────────────────

def stratified_sample(
    games: list[chess.pgn.Game],
    max_games: int,
    seed: int = 42,
) -> list[chess.pgn.Game]:
    """Sample games with balanced results and diverse openings."""
    rng = random.Random(seed)

    # Group by result
    by_result: dict[str, list[chess.pgn.Game]] = {}
    for g in games:
        r = classify_result(g)
        by_result.setdefault(r, []).append(g)

    # Target: 35% white wins, 35% black wins, 30% draws
    targets = {
        "white_win": int(max_games * 0.35),
        "black_win": int(max_games * 0.35),
        "draw": int(max_games * 0.30),
    }

    sampled = []
    for result_type, target_n in targets.items():
        pool = by_result.get(result_type, [])
        if not pool:
            continue
        rng.shuffle(pool)
        # Within each result type, try to diversify openings
        by_eco: dict[str, list[chess.pgn.Game]] = {}
        for g in pool:
            eco = eco_category(g)
            by_eco.setdefault(eco, []).append(g)

        # Round-robin across ECO categories
        selected = []
        eco_keys = list(by_eco.keys())
        rng.shuffle(eco_keys)
        idx = 0
        while len(selected) < target_n and any(by_eco.values()):
            key = eco_keys[idx % len(eco_keys)]
            if by_eco.get(key):
                selected.append(by_eco[key].pop(0))
            idx += 1
            # Remove exhausted categories
            eco_keys = [k for k in eco_keys if by_eco.get(k)]
            if not eco_keys:
                break

        sampled.extend(selected)

    rng.shuffle(sampled)
    return sampled[:max_games]


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Filter and sample chess games")
    parser.add_argument("tier", choices=["tier1", "tier2"], help="Game tier")
    parser.add_argument("input_dir", type=str, help="Directory containing PGN files")
    parser.add_argument("--output", type=str, default=None,
                        help="Output directory (default: analysis/sampled/{tier}/)")
    parser.add_argument("--max-games", type=int, default=200,
                        help="Maximum games to sample (default: 200)")
    parser.add_argument("--min-moves", type=int, default=30,
                        help="Minimum half-moves per game (default: 30)")
    parser.add_argument("--min-elo", type=int, default=2500,
                        help="Minimum Elo for Tier 2 (default: 2500)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Just show statistics, don't write files")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"Error: {input_dir} not found", file=sys.stderr)
        sys.exit(1)

    # Find PGN files
    pgn_files = sorted(input_dir.glob("*.pgn"))
    if not pgn_files:
        print(f"No PGN files found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Tier: {args.tier}")
    print(f"Input: {input_dir} ({len(pgn_files)} PGN files)")
    print(f"Target: {args.max_games} games, min {args.min_moves} half-moves")
    print()

    # Parse all games
    all_games: list[chess.pgn.Game] = []
    for pgn_file in pgn_files:
        print(f"  Parsing {pgn_file.name}...", end=" ", flush=True)
        games = parse_games(pgn_file)
        print(f"{len(games)} games")
        for g in games:
            g.headers["SourceFile"] = pgn_file.name
        all_games.extend(games)

    print(f"\nTotal parsed: {len(all_games)} games")

    # Filter
    if args.tier == "tier1":
        filtered = filter_tier1(all_games, min_moves=args.min_moves)
    else:
        filtered = filter_tier2(all_games, min_moves=args.min_moves, min_elo=args.min_elo)

    print(f"After filtering: {len(filtered)} games")

    # Statistics
    results = Counter(classify_result(g) for g in filtered)
    ecos = Counter(eco_category(g) for g in filtered)
    move_counts = [game_move_count(g) for g in filtered]
    avg_moves = sum(move_counts) / len(move_counts) if move_counts else 0

    print(f"\nFiltered pool statistics:")
    print(f"  Results: {dict(results)}")
    print(f"  ECO categories: {dict(ecos)}")
    print(f"  Avg half-moves: {avg_moves:.0f}")
    if move_counts:
        print(f"  Move range: {min(move_counts)}-{max(move_counts)}")

    # Sample unique player pairs (for engine games) or events
    if args.tier == "tier1":
        pairs = Counter(
            f"{get_header(g, 'White')} vs {get_header(g, 'Black')}"
            for g in filtered
        )
        print(f"  Top matchups:")
        for pair, count in pairs.most_common(10):
            print(f"    {pair}: {count}")

    # Sample
    sampled = stratified_sample(filtered, args.max_games, seed=args.seed)
    print(f"\nSampled: {len(sampled)} games")

    sampled_results = Counter(classify_result(g) for g in sampled)
    sampled_ecos = Counter(eco_category(g) for g in sampled)
    print(f"  Results: {dict(sampled_results)}")
    print(f"  ECO: {dict(sampled_ecos)}")

    if args.dry_run:
        print("\n(Dry run — no files written)")
        return

    # Write output
    if args.output is None:
        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        output_dir = project_root / "analysis" / "sampled" / args.tier
    else:
        output_dir = Path(args.output)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write as single multi-game PGN (efficient for batch processing)
    output_pgn = output_dir / f"{args.tier}_sampled.pgn"
    with open(output_pgn, "w") as f:
        for i, game in enumerate(sampled):
            # Tag with tier metadata
            game.headers["Tier"] = args.tier
            game.headers["SampleIndex"] = str(i)
            pgn_text = game_to_pgn_text(game)
            f.write(pgn_text)
            f.write("\n\n")

    print(f"\nWrote {len(sampled)} games → {output_pgn}")
    print(f"File size: {output_pgn.stat().st_size / 1024:.0f} KB")
    print(f"\nNext: python batch_cache_games.py {output_pgn}")


if __name__ == "__main__":
    main()
