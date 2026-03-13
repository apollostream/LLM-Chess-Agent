/** Clickable critical moments timeline bar with selection for Game Story. */

import type { CriticalMoment } from "../../api/types";

const COLORS: Record<string, string> = {
  blunder: "var(--blunder)",
  mistake: "var(--mistake)",
  inaccuracy: "var(--inaccuracy)",
  good: "var(--good)",
  excellent: "var(--excellent)",
  best: "var(--best)",
};

/** Unique key for a moment (move_number + side is unique per game). */
export function momentKey(m: CriticalMoment): string {
  return `${m.move_number}${m.side}`;
}

/** Pick the top N moments by |delta_cp| magnitude. */
export function topMomentsByMagnitude(moments: CriticalMoment[], n: number): Set<string> {
  const sorted = [...moments].sort((a, b) => Math.abs(b.delta_cp) - Math.abs(a.delta_cp));
  return new Set(sorted.slice(0, n).map(momentKey));
}

interface Props {
  moments: CriticalMoment[];
  totalMoves: number;
  selected: Set<string>;
  onClickMoment: (moment: CriticalMoment) => void;
  onToggleSelect: (moment: CriticalMoment) => void;
}

export function CriticalMoments({ moments, totalMoves, selected, onClickMoment, onToggleSelect }: Props) {
  if (moments.length === 0) return null;

  const selectedCount = moments.filter((m) => selected.has(momentKey(m))).length;

  return (
    <div className="moments-section fade-in">
      <div className="moments-label">
        Critical Moments ({moments.length})
        {selectedCount > 0 && (
          <span style={{ color: "var(--accent-text)", marginLeft: 8 }}>
            {selectedCount} selected for story
          </span>
        )}
      </div>
      <div className="moments-label" style={{ fontSize: 10, marginTop: -2, color: "var(--text-tertiary)" }}>
        Click to jump &middot; Shift+click to select/deselect for Game Story
      </div>
      <div className="moments-bar">
        {moments.map((m, i) => {
          const halfMove = (m.move_number - 1) * 2 + (m.side === "black" ? 1 : 0);
          const pct = totalMoves > 0 ? Math.max(2, Math.min(98, (halfMove / (totalMoves * 2)) * 100)) : 0;
          const color = COLORS[m.classification] ?? "var(--text-tertiary)";
          const isSelected = selected.has(momentKey(m));

          return (
            <button
              key={i}
              onClick={(e) => {
                if (e.shiftKey) {
                  onToggleSelect(m);
                } else {
                  onClickMoment(m);
                }
              }}
              className={`moment-dot ${isSelected ? "selected" : ""}`}
              style={{ left: `${pct}%` }}
              title={`${m.move_number}${m.side === "black" ? "..." : "."} ${m.san} (${m.classification}, ${m.delta_cp > 0 ? "+" : ""}${m.delta_cp}cp)${isSelected ? " [SELECTED]" : ""}`}
            >
              <span
                className="moment-pip"
                style={{
                  background: color,
                  transform: isSelected ? "scale(1.4)" : undefined,
                  boxShadow: isSelected ? `0 0 8px ${color}` : undefined,
                  outline: isSelected ? "2px solid var(--accent)" : undefined,
                  outlineOffset: 2,
                }}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}
