"""Agent streaming endpoints: /agent/stream, /agent/synopsis."""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.agent_service import stream_agent
from services.cache import agent_cache

router = APIRouter(prefix="/api/v1", tags=["agent"])


class AgentRequest(BaseModel):
    mode: str  # "guide" | "deep"
    fen: str | None = None
    analysis_json: str | None = None
    engine_json: str | None = None
    depth: int = 20
    lines: int = 3


class SynopsisRequest(BaseModel):
    moments: list[dict]
    pgn: str
    depth: int = 20
    lines: int = 3


def _cache_parts(req: AgentRequest) -> tuple[str, ...]:
    """Build cache key parts from request fields."""
    if req.mode == "deep":
        return (req.mode, req.fen or "")
    else:
        # "guide" mode: keyed by FEN + depth + lines (engine output is deterministic)
        return ("guide", req.fen or "", str(req.depth), str(req.lines))


async def _cached_stream(text: str) -> AsyncIterator[str]:
    """Replay cached text as SSE events."""
    yield f"data: {text}\n\n"
    yield "event: done\ndata: {}\n\n"


async def _caching_stream(req: AgentRequest, parts: tuple[str, ...]) -> AsyncIterator[str]:
    """Stream from agent, accumulate text, and cache the result."""
    accumulated: list[str] = []
    async for chunk in stream_agent(
        mode=req.mode,
        fen=req.fen,
        analysis_json=req.analysis_json,
        engine_json=req.engine_json,
        depth=req.depth,
        lines=req.lines,
    ):
        # Extract text content from SSE data lines
        if chunk.startswith("data: "):
            accumulated.append(chunk[6:].rstrip("\n"))
        yield chunk

    if accumulated:
        agent_cache.put(*parts, value="".join(accumulated))


@router.post("/agent/stream")
async def agent_stream(req: AgentRequest):
    parts = _cache_parts(req)
    cached = agent_cache.get(*parts)

    if cached is not None:
        return StreamingResponse(
            _cached_stream(cached),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return StreamingResponse(
        _caching_stream(req, parts),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/agent/synopsis")
async def agent_synopsis(req: SynopsisRequest):
    from services.synopsis_service import stream_synopsis

    # Cache key from sorted moment keys
    moment_keys = sorted(f"{m['move_number']}{m['side']}" for m in req.moments)
    cache_parts = ("synopsis", ",".join(moment_keys))
    cached = agent_cache.get(*cache_parts)

    if cached is not None:
        return StreamingResponse(
            _cached_stream(cached),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def _caching_synopsis() -> AsyncIterator[str]:
        accumulated: list[str] = []
        async for chunk in stream_synopsis(
            moments=req.moments,
            pgn=req.pgn,
            depth=req.depth,
            lines=req.lines,
        ):
            if chunk.startswith("data: "):
                try:
                    event = json.loads(chunk[6:].rstrip("\n"))
                    # Only accumulate text events (the final synopsis)
                    if event.get("type") == "text":
                        accumulated.append(chunk[6:].rstrip("\n"))
                except json.JSONDecodeError:
                    accumulated.append(chunk[6:].rstrip("\n"))
            yield chunk

        if accumulated:
            agent_cache.put(*cache_parts, value="".join(accumulated))

    return StreamingResponse(
        _caching_synopsis(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
