#!/usr/bin/env python3
"""Extract imbalance feature tables from game cache files.

Reads game cache JSON files (from analysis/game_cache/) and produces CSV tables
suitable for statistical analysis, clustering, and graphical modeling.

Three extraction modes:
  --mode game    : One row per game position — absolute features + eval + deltas (default)
  --mode stm     : STM-relative features — color-agnostic, universal archetypes
  --mode pv      : PV1 vs PVN comparison — structural diff at each position

Usage:
    # Process all cached games, output game transitions
    python extract_features.py --mode game --output analysis/features_game.csv

    # Process a single game cache, compare PVs
    python extract_features.py --mode pv --input analysis/game_cache/abc123.json --output analysis/features_pv.csv

    # Limit positions per game (for quick exploration)
    python extract_features.py --mode game --max-positions 20

    # Control PV replay depth
    python extract_features.py --mode pv --pv-depth 5
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

# Add scripts to path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from pv_state_chain import build_game_transition_table, build_game_stm_table, build_pv_comparison_table


GAME_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "analysis" / "game_cache"


def load_caches(input_path: str | None = None) -> list[tuple[Path, dict]]:
    """Load game cache files — single file or all from game_cache/."""
    if input_path:
        p = Path(input_path)
        if not p.exists():
            print(f"Error: {p} not found", file=sys.stderr)
            sys.exit(1)
        with open(p) as f:
            return [(p, json.load(f))]

    if not GAME_CACHE_DIR.exists():
        print(f"Error: {GAME_CACHE_DIR} not found", file=sys.stderr)
        sys.exit(1)

    caches = []
    for f in sorted(GAME_CACHE_DIR.glob("*.json")):
        with open(f) as fh:
            caches.append((f, json.load(fh)))
    return caches


def extract_game(caches: list[tuple[Path, dict]], max_positions: int | None, output: str) -> None:
    """Extract game transition tables to CSV."""
    all_rows: list[dict] = []

    for path, cache in caches:
        game_id = cache.get("pgn_hash", "unknown")[:12]
        n_pos = len(cache.get("positions", []))
        print(f"  {path.name}: {n_pos} positions (game {game_id})")

        rows = build_game_transition_table(cache, max_positions=max_positions)
        all_rows.extend(rows)

    _write_csv(all_rows, output)


def extract_stm(caches: list[tuple[Path, dict]], max_positions: int | None, output: str) -> None:
    """Extract STM-relative game transition tables to CSV."""
    all_rows: list[dict] = []

    for path, cache in caches:
        game_id = cache.get("pgn_hash", "unknown")[:12]
        n_pos = len(cache.get("positions", []))
        print(f"  {path.name}: {n_pos} positions (game {game_id})")

        rows = build_game_stm_table(cache, max_positions=max_positions)
        all_rows.extend(rows)

    _write_csv(all_rows, output)


def extract_pv(
    caches: list[tuple[Path, dict]],
    pv_depth: int,
    max_positions: int | None,
    output: str,
) -> None:
    """Extract PV comparison tables to CSV."""
    all_rows: list[dict] = []

    for path, cache in caches:
        game_id = cache.get("pgn_hash", "unknown")[:12]
        n_pos = len(cache.get("positions", []))
        print(f"  {path.name}: {n_pos} positions (game {game_id})")

        rows = build_pv_comparison_table(cache, pv_depth=pv_depth, max_positions=max_positions)
        all_rows.extend(rows)

    _write_csv(all_rows, output)


def _write_csv(rows: list[dict], output: str) -> None:
    """Write list of dicts to CSV."""
    if not rows:
        print("No data to write.", file=sys.stderr)
        return

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Collect all column names across all rows (row 0 may lack delta columns)
    all_keys: dict[str, None] = {}
    for row in rows:
        for k in row:
            all_keys[k] = None
    fieldnames = list(all_keys)

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows × {len(fieldnames)} columns → {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Extract imbalance features from game caches")
    parser.add_argument("--mode", choices=["game", "stm", "pv"], default="game",
                        help="Extraction mode (default: game)")
    parser.add_argument("--input", type=str, default=None,
                        help="Single game cache JSON file (default: all in game_cache/)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output CSV path (default: analysis/features_{mode}.csv)")
    parser.add_argument("--max-positions", type=int, default=None,
                        help="Max positions per game to process")
    parser.add_argument("--pv-depth", type=int, default=3,
                        help="PV replay depth for pv mode (default: 3)")
    args = parser.parse_args()

    if args.output is None:
        args.output = f"analysis/features_{args.mode}.csv"

    print(f"Mode: {args.mode}")
    print(f"Loading game caches...")
    caches = load_caches(args.input)
    print(f"Found {len(caches)} game(s)\n")

    t0 = time.time()

    if args.mode == "game":
        extract_game(caches, args.max_positions, args.output)
    elif args.mode == "stm":
        extract_stm(caches, args.max_positions, args.output)
    else:
        extract_pv(caches, args.pv_depth, args.max_positions, args.output)

    elapsed = time.time() - t0
    print(f"Elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
