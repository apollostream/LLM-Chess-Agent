"""Narrative endpoint: /narrative."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from models.schemas import NarrativeRequest
from services import narrative_service

router = APIRouter(prefix="/api/v1", tags=["narrative"])


@router.post("/narrative")
async def narrative(req: NarrativeRequest):
    if not req.pgn.strip():
        raise HTTPException(status_code=422, detail="PGN text is required")

    try:
        moments = await asyncio.to_thread(
            narrative_service.get_critical_moments,
            req.pgn, req.depth, req.threshold_cp, req.decay_scale_cp,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Narrative analysis failed: {e}")

    return {"critical_moments": moments, "count": len(moments)}
