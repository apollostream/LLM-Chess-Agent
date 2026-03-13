/** FEN paste / PGN upload input. */

import { useState } from "react";

interface Props {
  onFenSubmit: (fen: string) => void;
  onPgnSubmit: (pgn: string) => void;
}

export function PositionInput({ onFenSubmit, onPgnSubmit }: Props) {
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"fen" | "pgn">("fen");

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    if (mode === "fen") {
      onFenSubmit(trimmed);
    } else {
      onPgnSubmit(trimmed);
    }
  };

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setInput(text);
    setMode("pgn");
  };

  return (
    <div className="input-area">
      <div className="input-tabs">
        <button
          onClick={() => setMode("fen")}
          className={`input-tab ${mode === "fen" ? "active" : ""}`}
        >
          FEN
        </button>
        <button
          onClick={() => setMode("pgn")}
          className={`input-tab ${mode === "pgn" ? "active" : ""}`}
        >
          PGN
        </button>
        <label className="input-upload">
          Upload .pgn
          <input
            type="file"
            accept=".pgn"
            onChange={handleFile}
            style={{ display: "none" }}
          />
        </label>
      </div>

      {mode === "fen" ? (
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
          className="input-field"
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        />
      ) : (
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Paste PGN text here..."
          rows={5}
          className="input-field"
        />
      )}

      <div>
        <button onClick={handleSubmit} className="btn btn-primary">
          {mode === "fen" ? "Set Position" : "Load Game"}
        </button>
      </div>
    </div>
  );
}
