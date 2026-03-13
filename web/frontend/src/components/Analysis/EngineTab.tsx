/** Engine evaluation tab. */

import type { AnalysisResult } from "../../api/types";

interface Props {
  analysis: AnalysisResult;
}

export function EngineTab({ analysis }: Props) {
  const engine = analysis.engine;

  if (!engine || !engine.available) {
    return (
      <div className="engine-empty fade-in">
        Enable Stockfish below the board to see engine evaluation.
      </div>
    );
  }

  const ev = engine.eval;
  if (!ev) return <div className="engine-empty">No engine data.</div>;

  return (
    <div className="fade-in">
      <div className="engine-score">{ev.score_display}</div>
      <div className="engine-detail">
        <strong>Best:</strong> {ev.best_move}
      </div>
      {ev.pv && ev.pv.length > 0 && (
        <div className="engine-pv">{ev.pv.join(" ")}</div>
      )}
      {ev.wdl && (
        <div className="engine-wdl">
          W {ev.wdl.win / 10}% &middot; D {ev.wdl.draw / 10}% &middot; L {ev.wdl.loss / 10}%
        </div>
      )}
      <div className="engine-wdl" style={{ marginTop: 4 }}>
        Depth {ev.depth}
      </div>

      {engine.top_lines && engine.top_lines.length > 1 && (
        <div className="engine-lines">
          <div className="engine-lines-title">Top Lines</div>
          {engine.top_lines.map((line, i) => (
            <div key={i} className="engine-line">
              <span className="engine-line-num">{i + 1}.</span>
              <span className="engine-line-score">{line.score_display}</span>
              <span>{line.pv?.join(" ") ?? line.best_move}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
