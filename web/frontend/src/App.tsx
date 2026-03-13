import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import Markdown from "react-markdown";
import { ChessBoard } from "./components/Board/ChessBoard";
import { EvalBar } from "./components/Board/EvalBar";
import { tacticsToShapes } from "./components/Board/arrows";
import { PositionInput } from "./components/Input/PositionInput";
import { AnalysisPanel } from "./components/Analysis/AnalysisPanel";
import { MoveList } from "./components/Timeline/MoveList";
import { CriticalMoments, momentKey, topMomentsByMagnitude } from "./components/Timeline/CriticalMoments";
import { useChessGame } from "./hooks/useChessGame";
import { useAnalysis } from "./hooks/useAnalysis";
import { useSSE } from "./hooks/useSSE";
import { detectNarrative } from "./api/client";
import { openReport } from "./utils/exportReport";
import type { CriticalMoment } from "./api/types";

/** Cache key for Claude output: FEN|mode or synopsis|<moments hash> */
function cacheKey(fen: string, mode: string): string {
  return `${fen}|${mode}`;
}
function synopsisCacheKey(selected: Set<string>): string {
  return `synopsis|${[...selected].sort().join(",")}`;
}

function App() {
  const [game, actions] = useChessGame();
  const { analysis, loading, error, useEngine, setUseEngine } = useAnalysis(game.fen);
  const [pgnText, setPgnText] = useState<string | null>(null);

  const [moments, setMoments] = useState<CriticalMoment[]>([]);
  const [momentsLoading, setMomentsLoading] = useState(false);
  const [momentsError, setMomentsError] = useState<string | null>(null);
  const [selectedMoments, setSelectedMoments] = useState<Set<string>>(new Set());

  const [sseState, sseActions] = useSSE();

  // Cache Claude output by FEN+mode
  const claudeCache = useRef(new Map<string, string>());
  const [activeMode, setActiveMode] = useState<string | null>(null);
  const [cachedContent, setCachedContent] = useState<string | null>(null);

  // Track which synopsis key is active for caching
  const activeSynopsisKey = useRef<string | null>(null);

  // When streaming finishes, cache the result
  useEffect(() => {
    if (!sseState.streaming && sseState.data && activeMode) {
      const key = activeMode === "synopsis"
        ? activeSynopsisKey.current || "synopsis"
        : cacheKey(game.fen, activeMode);
      claudeCache.current.set(key, sseState.data);
    }
  }, [sseState.streaming, sseState.data, activeMode, game.fen]);

  // When FEN changes, check cache for previous Claude output.
  // Only auto-show cached content when not actively streaming.
  const prevFen = useRef(game.fen);
  useEffect(() => {
    if (prevFen.current === game.fen) return; // only on actual FEN change
    prevFen.current = game.fen;

    const guideCached = claudeCache.current.get(cacheKey(game.fen, "guide"));
    const deepCached = claudeCache.current.get(cacheKey(game.fen, "deep"));
    const cached = guideCached ?? deepCached ?? null;
    if (cached) {
      sseActions.reset();
      setActiveMode(guideCached ? "guide" : "deep");
    }
    setCachedContent(cached);
  }, [game.fen, sseActions]);

  // Determine what to display in Claude output
  const claudeContent = sseState.data || cachedContent || "";
  const showClaude = claudeContent || sseState.streaming || sseState.error;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft") { e.preventDefault(); actions.prev(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); actions.next(); }
      else if (e.key === "Home") { e.preventDefault(); actions.goToStart(); }
      else if (e.key === "End") { e.preventDefault(); actions.goToEnd(); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [actions]);

  const handleFen = useCallback(
    (fen: string) => { actions.setFen(fen); setPgnText(null); setMoments([]); setSelectedMoments(new Set()); },
    [actions],
  );

  const handlePgn = useCallback(
    (pgn: string) => {
      if (!actions.loadPgn(pgn)) { alert("Invalid PGN"); return; }
      setPgnText(pgn);
      setMoments([]);
      setSelectedMoments(new Set());
    },
    [actions],
  );

  const handleDetectMoments = useCallback(async () => {
    if (!pgnText) return;
    setMomentsLoading(true);
    setMomentsError(null);
    try {
      const result = await detectNarrative({ pgn: pgnText });
      setMoments(result.critical_moments);
      // Auto-select top 5 by eval swing magnitude
      setSelectedMoments(topMomentsByMagnitude(result.critical_moments, 5));
    } catch (err) {
      setMomentsError((err as Error).message);
    } finally {
      setMomentsLoading(false);
    }
  }, [pgnText]);

  const handleToggleMoment = useCallback((m: CriticalMoment) => {
    setSelectedMoments((prev) => {
      const next = new Set(prev);
      const key = momentKey(m);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const handleMomentClick = useCallback(
    (m: CriticalMoment) => {
      // Navigate to position BEFORE the critical move (fen_before)
      // so the board matches what was analyzed and cached
      const halfMove = (m.move_number - 1) * 2 + (m.side === "black" ? 1 : 0);
      actions.goToMove(halfMove);
    },
    [actions],
  );

  const handleAnalyze = useCallback(() => {
    if (!game.fen || !analysis) return;
    setActiveMode("guide");
    setCachedContent(null);
    sseActions.start("/api/v1/agent/stream", {
      mode: "guide",
      fen: game.fen,
      analysis_json: JSON.stringify(analysis),
      engine_json: analysis.engine ? JSON.stringify({
        eval: analysis.engine.eval,
        top_lines: analysis.engine.top_lines,
      }) : undefined,
    });
  }, [game.fen, analysis, sseActions]);

  const handleDeepAnalysis = useCallback(() => {
    if (!game.fen) return;
    setActiveMode("deep");
    setCachedContent(null);
    sseActions.start("/api/v1/agent/stream", {
      mode: "deep", fen: game.fen, analysis_json: analysis ? JSON.stringify(analysis) : undefined,
    });
  }, [game.fen, analysis, sseActions]);

  const handleSynopsis = useCallback(() => {
    if (!pgnText || selectedMoments.size === 0) return;
    const sKey = synopsisCacheKey(selectedMoments);
    const cached = claudeCache.current.get(sKey);
    if (cached) {
      sseActions.reset();
      setActiveMode("synopsis");
      activeSynopsisKey.current = sKey;
      setCachedContent(cached);
      return;
    }
    const selected = moments.filter((m) => selectedMoments.has(momentKey(m)));
    setActiveMode("synopsis");
    activeSynopsisKey.current = sKey;
    setCachedContent(null);
    sseActions.start("/api/v1/agent/synopsis", {
      moments: selected, pgn: pgnText,
    });
  }, [pgnText, moments, selectedMoments, sseActions]);

  const handleExport = useCallback(() => {
    if (!claudeContent) return;
    const selected = moments.filter((m) => selectedMoments.has(momentKey(m)));
    openReport({
      markdown: claudeContent,
      mode: activeMode || "guide",
      moments: activeMode === "synopsis" ? selected : undefined,
    });
  }, [claudeContent, activeMode, moments, selectedMoments]);

  const shapes = useMemo(() => {
    if (!analysis?.tactics) return [];
    return tacticsToShapes(analysis.tactics);
  }, [analysis]);

  const scoreCp = analysis?.engine?.eval?.score_cp ?? null;
  const mateIn = analysis?.engine?.eval?.mate_in ?? null;

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">
          Chess <span className="app-title-accent">Imbalances</span>
        </h1>
        <span className="app-subtitle">Silman's Framework</span>
      </header>

      <PositionInput onFenSubmit={handleFen} onPgnSubmit={handlePgn} />

      <div className="app-main">
        {/* Board Column */}
        <div className="board-column">
          <div className="board-frame">
            <EvalBar scoreCp={scoreCp} mateIn={mateIn} />
            <ChessBoard fen={game.fen} shapes={shapes} />
          </div>

          <label className="engine-toggle">
            <input
              type="checkbox"
              checked={useEngine}
              onChange={(e) => setUseEngine(e.target.checked)}
            />
            Stockfish evaluation
          </label>

          {game.hasGame && (
            <div>
              <div className="move-nav">
                <button onClick={actions.goToStart} className="btn-icon">&#x23EE;</button>
                <button onClick={actions.prev} className="btn-icon">&#x25C0;</button>
                <button onClick={actions.next} className="btn-icon">&#x25B6;</button>
                <button onClick={actions.goToEnd} className="btn-icon">&#x23ED;</button>
                <span className="move-counter">
                  {game.currentIndex} / {game.totalMoves}
                </span>
              </div>
              <MoveList
                moves={game.moves}
                currentIndex={game.currentIndex}
                onGoToMove={actions.goToMove}
              />
            </div>
          )}

          {game.hasGame && (
            <div>
              {moments.length === 0 && !momentsLoading && (
                <button
                  onClick={handleDetectMoments}
                  disabled={!pgnText}
                  className="btn btn-secondary"
                >
                  Detect Critical Moments
                </button>
              )}
              {momentsLoading && (
                <div className="analysis-loading pulse" style={{ fontSize: 12 }}>
                  Sweeping all moves with Stockfish...
                </div>
              )}
              {momentsError && (
                <div className="analysis-error" style={{ fontSize: 12 }}>{momentsError}</div>
              )}
              <CriticalMoments
                moments={moments}
                totalMoves={game.totalMoves}
                selected={selectedMoments}
                onClickMoment={handleMomentClick}
                onToggleSelect={handleToggleMoment}
              />
            </div>
          )}

          <div className="fen-display">{game.fen}</div>
        </div>

        {/* Panel Column */}
        <div className="panel-column">
          <AnalysisPanel analysis={analysis} loading={loading} error={error} />

          <div className="claude-actions">
            <button
              onClick={handleAnalyze}
              disabled={!analysis || sseState.streaming}
              className={`btn ${activeMode === "guide" ? "btn-primary" : "btn-secondary"}`}
            >
              Player's Guide
            </button>
            <button
              onClick={handleDeepAnalysis}
              disabled={sseState.streaming}
              className={`btn ${activeMode === "deep" ? "btn-primary" : "btn-secondary"}`}
            >
              Deep Analysis (BFIH)
            </button>
            {game.hasGame && selectedMoments.size > 0 && (
              <button
                onClick={handleSynopsis}
                disabled={sseState.streaming}
                className={`btn ${activeMode === "synopsis" ? "btn-primary" : "btn-secondary"}`}
              >
                Game Synopsis ({selectedMoments.size} moments)
              </button>
            )}
            {sseState.streaming && (
              <button onClick={sseActions.stop} className="btn btn-danger">
                Stop
              </button>
            )}
            {claudeContent && !sseState.streaming && (
              <button onClick={handleExport} className="btn btn-secondary">
                Export
              </button>
            )}
          </div>

          {sseState.progress && sseState.streaming && (
            <div className="synopsis-progress pulse">
              {sseState.progress.phase === "engine" &&
                `Evaluating positions ${sseState.progress.current}/${sseState.progress.total}...`}
              {sseState.progress.phase === "guide" &&
                `Analyzing position ${sseState.progress.current}/${sseState.progress.total}...`}
              {sseState.progress.phase === "synthesis" &&
                `Composing game synopsis...`}
            </div>
          )}

          {showClaude && (
            <div className="claude-output">
              {sseState.error && (
                <div className="analysis-error" style={{ marginBottom: 8 }}>
                  {sseState.error}
                </div>
              )}
              <Markdown>{claudeContent}</Markdown>
              {sseState.streaming && <span className="claude-cursor" />}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
