/** Hook for fetching and caching analysis by FEN. */

import { useState, useEffect, useRef, useCallback } from "react";
import { analyzePosition } from "../api/client";
import type { AnalysisResult } from "../api/types";

interface UseAnalysisResult {
  analysis: AnalysisResult | null;
  loading: boolean;
  error: string | null;
  useEngine: boolean;
  setUseEngine: (v: boolean) => void;
  clearCache: () => void;
}

export function useAnalysis(fen: string): UseAnalysisResult {
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useEngine, setUseEngine] = useState(true);
  const cache = useRef(new Map<string, AnalysisResult>());
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const fetchAnalysis = useCallback((fen: string, engine: boolean) => {
    const cacheKey = `${fen}|${engine}`;

    const cached = cache.current.get(cacheKey);
    if (cached) {
      setAnalysis(cached);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);

    analyzePosition({ fen, use_engine: engine })
      .then((result) => {
        cache.current.set(cacheKey, result);
        setAnalysis(result);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    debounceRef.current = setTimeout(() => {
      fetchAnalysis(fen, useEngine);
    }, 150);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [fen, useEngine, fetchAnalysis]);

  const clearCache = useCallback(() => {
    cache.current.clear();
  }, []);

  return { analysis, loading, error, useEngine, setUseEngine, clearCache };
}
