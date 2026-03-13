/** Chess game state management using chess.js. */

import { useState, useCallback, useMemo } from "react";
import { Chess } from "chess.js";

export interface ChessGameState {
  /** Current FEN at the viewed position. */
  fen: string;
  /** All moves in SAN notation. */
  moves: string[];
  /** Current half-move index (0 = initial position, 1 = after first move, etc.). */
  currentIndex: number;
  /** Total number of half-moves. */
  totalMoves: number;
  /** Whether a PGN game is loaded. */
  hasGame: boolean;
}

export interface ChessGameActions {
  /** Set position from FEN string (clears any loaded game). */
  setFen: (fen: string) => void;
  /** Load a PGN game. Returns true on success. */
  loadPgn: (pgn: string) => boolean;
  /** Navigate to a specific half-move index. */
  goToMove: (index: number) => void;
  /** Go to next move. */
  next: () => void;
  /** Go to previous move. */
  prev: () => void;
  /** Go to start. */
  goToStart: () => void;
  /** Go to end. */
  goToEnd: () => void;
}

const STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export function useChessGame(): [ChessGameState, ChessGameActions] {
  const [fen, setFenState] = useState(STARTING_FEN);
  const [moves, setMoves] = useState<string[]>([]);
  const [fens, setFens] = useState<string[]>([STARTING_FEN]);
  const [currentIndex, setCurrentIndex] = useState(0);

  const setFen = useCallback((newFen: string) => {
    setFenState(newFen);
    setMoves([]);
    setFens([newFen]);
    setCurrentIndex(0);
  }, []);

  const loadPgn = useCallback((pgn: string): boolean => {
    const game = new Chess();
    try {
      game.loadPgn(pgn);
    } catch {
      return false;
    }

    const history = game.history();
    const positions: string[] = [STARTING_FEN];

    // Replay to collect FENs at each position
    const replay = new Chess();
    for (const san of history) {
      replay.move(san);
      positions.push(replay.fen());
    }

    setMoves(history);
    setFens(positions);
    setCurrentIndex(positions.length - 1);
    setFenState(positions[positions.length - 1]);
    return true;
  }, []);

  const goToMove = useCallback(
    (index: number) => {
      const clamped = Math.max(0, Math.min(index, fens.length - 1));
      setCurrentIndex(clamped);
      setFenState(fens[clamped]);
    },
    [fens],
  );

  const next = useCallback(() => goToMove(currentIndex + 1), [goToMove, currentIndex]);
  const prev = useCallback(() => goToMove(currentIndex - 1), [goToMove, currentIndex]);
  const goToStart = useCallback(() => goToMove(0), [goToMove]);
  const goToEnd = useCallback(() => goToMove(fens.length - 1), [goToMove, fens]);

  const state: ChessGameState = useMemo(
    () => ({
      fen,
      moves,
      currentIndex,
      totalMoves: moves.length,
      hasGame: moves.length > 0,
    }),
    [fen, moves, currentIndex],
  );

  const actions: ChessGameActions = useMemo(
    () => ({ setFen, loadPgn, goToMove, next, prev, goToStart, goToEnd }),
    [setFen, loadPgn, goToMove, next, prev, goToStart, goToEnd],
  );

  return [state, actions];
}
