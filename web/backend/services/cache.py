"""FEN-keyed in-memory cache for analysis results."""

from __future__ import annotations

import hashlib
from typing import Any


class AnalysisCache:
    """Simple in-memory cache keyed by FEN (and optional extra params)."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    @staticmethod
    def _key(fen: str, *extras: Any) -> str:
        raw = fen + "|" + "|".join(str(e) for e in extras)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, fen: str, *extras: Any) -> Any | None:
        return self._store.get(self._key(fen, *extras))

    def put(self, fen: str, *extras: Any, value: Any) -> None:
        self._store[self._key(fen, *extras)] = value

    def clear(self) -> None:
        self._store.clear()


class AgentCache:
    """Cache for completed agent streaming results, keyed by content hash."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    @staticmethod
    def _key(*parts: str) -> str:
        raw = "|".join(p or "" for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, *parts: str) -> str | None:
        return self._store.get(self._key(*parts))

    def put(self, *parts: str, value: str) -> None:
        self._store[self._key(*parts)] = value


# Module-level singletons
analysis_cache = AnalysisCache()
tactics_cache = AnalysisCache()
engine_cache = AnalysisCache()
agent_cache = AgentCache()
