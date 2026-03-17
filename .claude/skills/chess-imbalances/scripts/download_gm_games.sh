#!/bin/bash
# Download grandmaster and engine games for the causality dataset.
#
# Three tiers:
#   Tier 1: Super-engine games (TCEC Superfinals + Premier Division)
#   Tier 2: Super-GM games (PGN Mentor top players + Lichess Elite)
#   Tier 3: Already cached intermediate games (no download needed)
#
# Usage:
#   bash download_gm_games.sh [--tier1] [--tier2] [--all]
#   Default: --all

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DOWNLOAD_DIR="$PROJECT_ROOT/analysis/downloads"

mkdir -p "$DOWNLOAD_DIR/tier1_engines" "$DOWNLOAD_DIR/tier2_gm"

# Parse args
TIER1=false
TIER2=false
if [[ $# -eq 0 ]] || [[ "$*" == *"--all"* ]]; then
    TIER1=true
    TIER2=true
else
    [[ "$*" == *"--tier1"* ]] && TIER1=true
    [[ "$*" == *"--tier2"* ]] && TIER2=true
fi

echo "=== Chess Games Acquisition ==="
echo "Download directory: $DOWNLOAD_DIR"
echo ""

# ─── Tier 1: Super-Engine Games ──────────────────────────────────────────────
if $TIER1; then
    echo "── Tier 1: Super-Engine Games (TCEC) ──"

    TCEC_ZIP="$DOWNLOAD_DIR/tier1_engines/TCEC-everything-compact.zip"
    if [[ -f "$TCEC_ZIP" ]]; then
        echo "  SKIP: TCEC archive already downloaded"
    else
        echo "  Downloading TCEC Season 1-28 compact archive (~23MB)..."
        wget -q --show-progress -O "$TCEC_ZIP" \
            "https://github.com/TCEC-Chess/tcecgames/releases/download/S28-final/TCEC-everything-compact.zip"
    fi

    # Extract PGN files from zip
    TCEC_DIR="$DOWNLOAD_DIR/tier1_engines/tcec"
    if [[ -d "$TCEC_DIR" ]] && ls "$TCEC_DIR"/*.pgn 1>/dev/null 2>&1; then
        echo "  SKIP: TCEC PGNs already extracted"
    else
        echo "  Extracting TCEC PGN files..."
        mkdir -p "$TCEC_DIR"
        unzip -o -q "$TCEC_ZIP" -d "$TCEC_DIR"
        echo "  Extracted $(ls "$TCEC_DIR"/*.pgn 2>/dev/null | wc -l) PGN files"
    fi

    echo ""
fi

# ─── Tier 2: Super-GM Games ─────────────────────────────────────────────────
if $TIER2; then
    echo "── Tier 2: Super-GM Games ──"

    # PGN Mentor — top player collections
    PLAYERS=("Carlsen" "Caruana" "Firouzja" "Ding" "Nepomniachtchi" "So")
    for player in "${PLAYERS[@]}"; do
        ZIP="$DOWNLOAD_DIR/tier2_gm/${player}.zip"
        PGN="$DOWNLOAD_DIR/tier2_gm/${player}.pgn"
        if [[ -f "$PGN" ]]; then
            echo "  SKIP: ${player}.pgn already exists"
        elif [[ -f "$ZIP" ]]; then
            echo "  Extracting ${player}.zip..."
            unzip -o -q "$ZIP" -d "$DOWNLOAD_DIR/tier2_gm/"
        else
            echo "  Downloading ${player} games from PGN Mentor..."
            wget -q --show-progress -O "$ZIP" \
                "https://www.pgnmentor.com/players/${player}.zip" || {
                echo "  WARNING: Failed to download ${player}. Skipping."
                continue
            }
            unzip -o -q "$ZIP" -d "$DOWNLOAD_DIR/tier2_gm/"
        fi
    done

    # Lichess Elite Database — recent month
    ELITE_ZIP="$DOWNLOAD_DIR/tier2_gm/lichess_elite_2025-11.zip"
    ELITE_PGN="$DOWNLOAD_DIR/tier2_gm/lichess_elite_2025-11.pgn"
    if [[ -f "$ELITE_PGN" ]]; then
        echo "  SKIP: Lichess Elite 2025-11 already extracted"
    elif [[ -f "$ELITE_ZIP" ]]; then
        echo "  Extracting Lichess Elite 2025-11..."
        unzip -o -q "$ELITE_ZIP" -d "$DOWNLOAD_DIR/tier2_gm/"
    else
        echo "  Downloading Lichess Elite DB (Nov 2025, ~65MB)..."
        wget -q --show-progress -O "$ELITE_ZIP" \
            "https://database.nikonoel.fr/lichess_elite_2025-11.zip" || {
            echo "  WARNING: Failed to download Lichess Elite. Skipping."
        }
        if [[ -f "$ELITE_ZIP" ]]; then
            unzip -o -q "$ELITE_ZIP" -d "$DOWNLOAD_DIR/tier2_gm/"
        fi
    fi

    echo ""
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo "=== Download Summary ==="
echo "Tier 1 (engines):"
if [[ -d "$DOWNLOAD_DIR/tier1_engines/tcec" ]]; then
    echo "  TCEC PGNs: $(ls "$DOWNLOAD_DIR/tier1_engines/tcec/"*.pgn 2>/dev/null | wc -l) files"
    for f in "$DOWNLOAD_DIR/tier1_engines/tcec/"*.pgn; do
        if [[ -f "$f" ]]; then
            count=$(grep -c '^\[Event ' "$f" 2>/dev/null || echo 0)
            echo "    $(basename "$f"): $count games"
        fi
    done
fi

echo ""
echo "Tier 2 (GMs):"
for f in "$DOWNLOAD_DIR/tier2_gm/"*.pgn; do
    if [[ -f "$f" ]]; then
        count=$(grep -c '^\[Event ' "$f" 2>/dev/null || echo 0)
        size=$(du -h "$f" | cut -f1)
        echo "  $(basename "$f"): $count games ($size)"
    fi
done

echo ""
echo "Next step: python sample_games.py to filter and sample from these files"
