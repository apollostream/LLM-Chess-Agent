"""Pydantic request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    fen: str
    use_engine: bool = False
    depth: int = Field(default=20, ge=1, le=30)
    lines: int = Field(default=3, ge=1, le=5)


class TacticsRequest(BaseModel):
    fen: str


class EngineRequest(BaseModel):
    fen: str
    depth: int = Field(default=20, ge=1, le=30)
    lines: int = Field(default=3, ge=1, le=5)


class ClassifyRequest(BaseModel):
    fen: str
    move: str  # SAN notation
    depth: int = Field(default=20, ge=1, le=30)


class NarrativeRequest(BaseModel):
    pgn: str
    depth: int = Field(default=18, ge=1, le=25)
    threshold_cp: int = Field(default=50, ge=10, le=200)
    decay_scale_cp: int | None = Field(default=750, ge=100, le=2000)
