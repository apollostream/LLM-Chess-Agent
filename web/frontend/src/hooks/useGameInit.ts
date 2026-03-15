/** Hook for game initialization — bulk engine eval + critical moment detection. */

import { useState, useCallback, useRef } from "react";
import type { CriticalMoment, GameInitEvent } from "../api/types";

interface GameInitProgress {
  phase: "parse" | "engine" | "moments";
  current: number;
  total: number;
}

export interface GameInitState {
  status: "idle" | "evaluating" | "ready" | "error";
  gameId: string | null;
  progress: GameInitProgress | null;
  moments: CriticalMoment[];
  momentsAll: CriticalMoment[];
  cached: boolean;
  error: string | null;
}

export interface GameInitActions {
  initialize: (pgn: string, depth?: number) => void;
  regenerate: () => void;
  reset: () => void;
}

const INITIAL_STATE: GameInitState = {
  status: "idle",
  gameId: null,
  progress: null,
  moments: [],
  momentsAll: [],
  cached: false,
  error: null,
};

export function useGameInit(): [GameInitState, GameInitActions] {
  const [state, setState] = useState<GameInitState>(INITIAL_STATE);
  const abortRef = useRef<AbortController | null>(null);
  const pgnRef = useRef<string | null>(null);
  const depthRef = useRef<number | undefined>(undefined);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const reset = useCallback(() => {
    stop();
    setState(INITIAL_STATE);
    pgnRef.current = null;
  }, [stop]);

  const initialize = useCallback(
    async (pgn: string, depth?: number) => {
      stop();
      pgnRef.current = pgn;
      depthRef.current = depth;
      setState({
        ...INITIAL_STATE,
        status: "evaluating",
      });

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch("/api/v1/game/init", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pgn, ...(depth !== undefined && { depth }) }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const messages = buffer.split("\n\n");
          buffer = messages.pop() ?? "";

          for (const msg of messages) {
            for (const line of msg.split("\n")) {
              if (!line.startsWith("data: ")) continue;
              const payload = line.slice(6);
              try {
                const event = JSON.parse(payload) as GameInitEvent;

                if (event.type === "progress") {
                  setState((prev) => ({
                    ...prev,
                    progress: {
                      phase: event.phase,
                      current: event.current,
                      total: event.total,
                    },
                  }));
                } else if (event.type === "cached") {
                  setState((prev) => ({
                    ...prev,
                    cached: true,
                    gameId: event.game_id,
                  }));
                } else if (event.type === "done") {
                  setState({
                    status: "ready",
                    gameId: event.game_id,
                    progress: null,
                    moments: event.moments as CriticalMoment[],
                    momentsAll: event.moments_all as CriticalMoment[],
                    cached: false,
                    error: null,
                  });
                } else if (event.type === "error") {
                  setState((prev) => ({
                    ...prev,
                    status: "error",
                    error: event.content,
                    progress: null,
                  }));
                }
              } catch {
                // skip malformed payloads
              }
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setState((prev) => ({
            ...prev,
            status: "error",
            error: (err as Error).message,
            progress: null,
          }));
        }
      }
    },
    [stop],
  );

  const regenerate = useCallback(() => {
    if (pgnRef.current) {
      initialize(pgnRef.current, depthRef.current);
    }
  }, [initialize]);

  return [state, { initialize, regenerate, reset }];
}
