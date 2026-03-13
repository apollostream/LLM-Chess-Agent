"""Analysis endpoints: /analyze, /tactics, /engine, /classify."""

from __future__ import annotations

import asyncio

import chess
from fastapi import APIRouter, HTTPException

from models.schemas import AnalyzeRequest, TacticsRequest, EngineRequest, ClassifyRequest
from services.cache import analysis_cache, tactics_cache, engine_cache
from services import chess_pipeline

router = APIRouter(prefix="/api/v1", tags=["analysis"])


def _validate_fen(fen: str) -> None:
    try:
        chess.Board(fen)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid FEN: {e}")


@router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    _validate_fen(req.fen)

    cached = analysis_cache.get(req.fen, req.use_engine, req.depth, req.lines)
    if cached is not None:
        return cached

    result = await asyncio.to_thread(
        chess_pipeline.analyze_position, req.fen, req.use_engine, req.depth, req.lines
    )
    analysis_cache.put(req.fen, req.use_engine, req.depth, req.lines, value=result)
    return result


@router.post("/tactics")
async def tactics(req: TacticsRequest):
    _validate_fen(req.fen)

    cached = tactics_cache.get(req.fen)
    if cached is not None:
        return cached

    result = await asyncio.to_thread(chess_pipeline.analyze_tactics, req.fen)
    tactics_cache.put(req.fen, value=result)
    return result


@router.post("/engine")
async def engine(req: EngineRequest):
    _validate_fen(req.fen)

    cached = engine_cache.get(req.fen, req.depth, req.lines)
    if cached is not None:
        return cached

    result = await asyncio.to_thread(
        chess_pipeline.evaluate_position, req.fen, req.depth, req.lines
    )
    if result is None:
        raise HTTPException(status_code=503, detail="Stockfish engine not available")
    engine_cache.put(req.fen, req.depth, req.lines, value=result)
    return result


@router.post("/classify")
async def classify(req: ClassifyRequest):
    _validate_fen(req.fen)

    try:
        result = await asyncio.to_thread(
            chess_pipeline.classify_move, req.fen, req.move, req.depth
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid move: {e}")

    if result is None:
        raise HTTPException(status_code=503, detail="Stockfish engine not available")
    return result
