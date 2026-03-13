/** Flat PGN move list — clickable half-moves with current highlighted. */

interface Props {
  moves: string[];
  currentIndex: number;
  onGoToMove: (index: number) => void;
}

export function MoveList({ moves, currentIndex, onGoToMove }: Props) {
  if (moves.length === 0) return null;

  const rows: { num: number; white: string; black?: string }[] = [];
  for (let i = 0; i < moves.length; i += 2) {
    rows.push({
      num: Math.floor(i / 2) + 1,
      white: moves[i],
      black: moves[i + 1],
    });
  }

  return (
    <div className="move-list">
      {rows.map((row) => {
        const whiteIdx = (row.num - 1) * 2 + 1;
        const blackIdx = whiteIdx + 1;

        return (
          <span key={row.num} className="move-pair">
            <span className="move-num">{row.num}.</span>
            <span
              onClick={() => onGoToMove(whiteIdx)}
              className={`move-san ${currentIndex === whiteIdx ? "active" : ""}`}
            >
              {row.white}
            </span>
            {row.black && (
              <span
                onClick={() => onGoToMove(blackIdx)}
                className={`move-san ${currentIndex === blackIdx ? "active" : ""}`}
              >
                {row.black}
              </span>
            )}{" "}
          </span>
        );
      })}
    </div>
  );
}
