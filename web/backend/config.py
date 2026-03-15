"""Configuration for the chess analysis backend."""

from pathlib import Path

# Project root (two levels up from web/backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Path to chess analysis scripts
SCRIPTS_DIR = PROJECT_ROOT / ".claude" / "skills" / "chess-imbalances" / "scripts"

# Stockfish engine settings
ENGINE_DEPTH_DEFAULT = 20
ENGINE_LINES_DEFAULT = 3

# Game init bulk evaluation defaults (depth 12 ≈ 13s for 97 positions)
GAME_INIT_DEPTH_DEFAULT = 12
GAME_INIT_LINES_DEFAULT = 3

# Narrative detection defaults
NARRATIVE_DEPTH_DEFAULT = 18
NARRATIVE_THRESHOLD_CP = 50
NARRATIVE_DECAY_SCALE_CP = 750
