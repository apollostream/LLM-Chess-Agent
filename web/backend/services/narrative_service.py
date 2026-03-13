"""Bridge to the game narrative pipeline."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from config import SCRIPTS_DIR, NARRATIVE_DEPTH_DEFAULT, NARRATIVE_THRESHOLD_CP, NARRATIVE_DECAY_SCALE_CP

_scripts_str = str(SCRIPTS_DIR)
if _scripts_str not in sys.path:
    sys.path.insert(0, _scripts_str)

from game_narrative import detect_critical_moments  # noqa: E402


def get_critical_moments(
    pgn_text: str,
    depth: int = NARRATIVE_DEPTH_DEFAULT,
    threshold_cp: int = NARRATIVE_THRESHOLD_CP,
    decay_scale_cp: int | None = NARRATIVE_DECAY_SCALE_CP,
) -> list[dict]:
    """Detect critical moments from PGN text.

    Writes PGN to a temp file since detect_critical_moments expects a path.
    Returns list of CriticalMoment dicts.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pgn", delete=False) as f:
        f.write(pgn_text)
        pgn_path = Path(f.name)

    try:
        moments = detect_critical_moments(
            pgn_path, depth=depth, threshold_cp=threshold_cp,
            decay_scale_cp=decay_scale_cp,
        )
        return [m.model_dump() for m in moments]
    finally:
        pgn_path.unlink(missing_ok=True)
