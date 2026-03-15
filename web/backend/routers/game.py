"""Game initialization and cache management endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import GAME_INIT_DEPTH_DEFAULT, GAME_INIT_LINES_DEFAULT
from services import game_store
from services.game_init_service import initialize_game

router = APIRouter(prefix="/api/v1", tags=["game"])


class GameInitRequest(BaseModel):
    pgn: str
    depth: int = Field(default=GAME_INIT_DEPTH_DEFAULT, ge=1, le=30)
    lines: int = Field(default=GAME_INIT_LINES_DEFAULT, ge=1, le=5)
    threshold_cp: int = Field(default=50, ge=10, le=200)
    decay_scale_cp: int | None = Field(default=750, ge=100, le=2000)


@router.post("/game/init")
async def game_init(req: GameInitRequest):
    """Initialize a game: parse PGN, evaluate all positions, detect moments.

    Returns an SSE stream with progress events and a final done event.
    """
    return StreamingResponse(
        initialize_game(
            pgn=req.pgn,
            depth=req.depth,
            lines=req.lines,
            threshold_cp=req.threshold_cp,
            decay_scale_cp=req.decay_scale_cp,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/game/state")
async def game_state():
    """Return info about the active game, or null if none."""
    g = game_store.active_game
    if g is None:
        return {"active": False}
    return {
        "active": True,
        "game_id": g.pgn_hash[:12],
        "positions": len(g.positions),
        "evals_count": len(g.engine_evals),
        "moments_all": len(g.critical_moments_all),
        "moments_selected": len(g.critical_moments_selected),
        "depth": g.depth,
        "lines": g.lines,
        "has_synopsis": g.synopsis_text is not None,
    }


@router.post("/game/save")
async def game_save():
    """Persist active game to disk."""
    g = game_store.active_game
    if g is None:
        return {"saved": False, "reason": "No active game"}
    path = game_store.save_to_disk(g)
    return {"saved": True, "path": str(path)}


@router.post("/game/clear")
async def game_clear():
    """Clear active game cache."""
    game_store.clear_active()
    return {"cleared": True}
