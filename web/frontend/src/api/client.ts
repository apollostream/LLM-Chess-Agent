/** API client — fetch wrappers for all backend endpoints. */

import type {
  AnalyzeRequest,
  AnalysisResult,
  TacticsRequest,
  TacticsResult,
  EngineRequest,
  ClassifyRequest,
  NarrativeRequest,
  NarrativeResponse,
} from "./types";

const BASE = "/api/v1";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || res.statusText);
  }
  return res.json();
}

export function analyzePosition(req: AnalyzeRequest): Promise<AnalysisResult> {
  return post("/analyze", req);
}

export function analyzeTactics(req: TacticsRequest): Promise<TacticsResult> {
  return post("/tactics", req);
}

export function evaluateEngine(req: EngineRequest) {
  return post<{ eval: unknown; top_lines: unknown[] }>("/engine", req);
}

export function classifyMove(req: ClassifyRequest) {
  return post<Record<string, unknown>>("/classify", req);
}

export function detectNarrative(req: NarrativeRequest): Promise<NarrativeResponse> {
  return post("/narrative", req);
}

export function saveGame(): Promise<{ saved: boolean; path?: string }> {
  return post("/game/save", {});
}

export function clearGame(): Promise<{ cleared: boolean }> {
  return post("/game/clear", {});
}
