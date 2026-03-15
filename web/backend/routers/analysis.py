"""Analysis endpoints: /analyze, /tactics, /engine, /classify, /board.svg."""

from __future__ import annotations

import asyncio

import chess
import chess.svg
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from models.schemas import AnalyzeRequest, TacticsRequest, EngineRequest, ClassifyRequest
from services.cache import analysis_cache, tactics_cache, engine_cache
from services import chess_pipeline
from services import game_store

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

    # When a game is active and engine data is cached, always inject it —
    # it's free (no Stockfish call) and keeps the Engine tab working.
    g = game_store.active_game
    if g and req.fen in g.engine_evals:
        result = await asyncio.to_thread(
            chess_pipeline.analyze_position, req.fen, False, req.depth, req.lines
        )
        result["engine"] = g.engine_evals[req.fen]
        analysis_cache.put(req.fen, req.use_engine, req.depth, req.lines, value=result)
        return result

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

    # Check game cache first (single source of truth)
    g = game_store.active_game
    if g and req.fen in g.engine_evals:
        return g.engine_evals[req.fen]

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


@router.get("/board.svg")
async def board_svg(
    fen: str = Query(..., description="FEN position string"),
    size: int = Query(360, ge=100, le=800),
):
    """Render a board position as SVG."""
    _validate_fen(fen)
    board = chess.Board(fen)
    svg = chess.svg.board(board, size=size)
    return Response(content=svg, media_type="image/svg+xml")
