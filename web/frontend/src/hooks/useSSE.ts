/** POST-based SSE streaming hook. */

import { useState, useCallback, useRef } from "react";

interface ProgressInfo {
  phase: "engine" | "guide" | "synthesis";
  current: number;
  total: number;
}

interface SSEState {
  data: string;
  prefix: string;
  streaming: boolean;
  error: string | null;
  progress: ProgressInfo | null;
}

interface SSEActions {
  start: (url: string, body: unknown) => void;
  stop: () => void;
  reset: () => void;
}

export function useSSE(): [SSEState, SSEActions] {
  const [data, setData] = useState("");
  const [prefix, setPrefix] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
    setProgress(null);
  }, []);

  const reset = useCallback(() => {
    stop();
    setData("");
    setPrefix("");
    setError(null);
  }, [stop]);

  const start = useCallback(
    async (url: string, body: unknown) => {
      stop();
      setData("");
      setPrefix("");
      setError(null);
      setProgress(null);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
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
          // Process complete SSE messages (terminated by double newline)
          const messages = buffer.split("\n\n");
          buffer = messages.pop() ?? ""; // last element may be incomplete

          for (const msg of messages) {
            for (const line of msg.split("\n")) {
              if (line.startsWith("data: ")) {
                const payload = line.slice(6);
                if (payload === "[DONE]") continue;
                try {
                  const event = JSON.parse(payload);
                  if (event.type === "text") {
                    setData((prev) => prev + event.content);
                  } else if (event.type === "opening_moves") {
                    setPrefix(event.content);
                  } else if (event.type === "progress") {
                    setProgress({
                      phase: event.phase,
                      current: event.current,
                      total: event.total,
                    });
                  }
                } catch {
                  // Not JSON — skip malformed payloads
                }
              }
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError((err as Error).message);
        }
      } finally {
        setStreaming(false);
        setProgress(null);
        abortRef.current = null;
      }
    },
    [stop],
  );

  return [{ data, prefix, streaming, error, progress }, { start, stop, reset }];
}
