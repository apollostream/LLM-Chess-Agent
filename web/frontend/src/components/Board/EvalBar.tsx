/** Vertical eval bar with smooth transitions. */

interface Props {
  scoreCp: number | null;
  mateIn: number | null;
  height?: number;
}

export function EvalBar({ scoreCp, mateIn, height = 520 }: Props) {
  let whitePercent = 50;
  let display = "0.0";

  if (mateIn !== null) {
    whitePercent = mateIn > 0 ? 100 : 0;
    display = `M${Math.abs(mateIn)}`;
  } else if (scoreCp !== null) {
    const pawns = scoreCp / 100;
    whitePercent = 50 + 50 * (2 / (1 + Math.exp(-0.5 * pawns)) - 1);
    display = pawns >= 0 ? `+${pawns.toFixed(1)}` : pawns.toFixed(1);
  }

  return (
    <div className="eval-bar" style={{ height }}>
      <div className="eval-bar-black" style={{ flex: `${100 - whitePercent}` }}>
        {whitePercent < 50 && <span>{display}</span>}
      </div>
      <div className="eval-bar-white" style={{ flex: `${whitePercent}` }}>
        {whitePercent >= 50 && <span>{display}</span>}
      </div>
    </div>
  );
}
