/** Chessground board wrapper. */

import { useRef, useEffect } from "react";
import { Chessground } from "chessground";
import type { Api } from "chessground/api";
import type { Config } from "chessground/config";
import type { DrawShape } from "chessground/draw";
import "chessground/assets/chessground.base.css";
import "chessground/assets/chessground.brown.css";
import "chessground/assets/chessground.cburnett.css";

interface Props {
  fen: string;
  orientation?: "white" | "black";
  shapes?: DrawShape[];
  width?: number;
}

export function ChessBoard({ fen, orientation = "white", shapes = [], width = 520 }: Props) {
  const boardRef = useRef<HTMLDivElement>(null);
  const apiRef = useRef<Api | null>(null);

  useEffect(() => {
    if (!boardRef.current) return;

    const config: Config = {
      fen,
      orientation,
      viewOnly: true,
      coordinates: true,
      drawable: {
        enabled: true,
        autoShapes: shapes,
      },
    };

    apiRef.current = Chessground(boardRef.current, config);

    return () => {
      apiRef.current?.destroy();
      apiRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    apiRef.current?.set({ fen, orientation });
  }, [fen, orientation]);

  useEffect(() => {
    apiRef.current?.set({
      drawable: { autoShapes: shapes },
    });
  }, [shapes]);

  return (
    <div
      ref={boardRef}
      style={{ width: `${width}px`, height: `${width}px`, borderRadius: "var(--radius-sm)" }}
    />
  );
}
