/** TypeScript interfaces mirroring the Python analysis JSON. */

export interface AnalyzeRequest {
  fen: string;
  use_engine?: boolean;
  depth?: number;
  lines?: number;
}

export interface TacticsRequest {
  fen: string;
}

export interface EngineRequest {
  fen: string;
  depth?: number;
  lines?: number;
}

export interface ClassifyRequest {
  fen: string;
  move: string;
  depth?: number;
}

export interface NarrativeRequest {
  pgn: string;
  depth?: number;
  threshold_cp?: number;
  decay_scale_cp?: number | null;
}

/** Engine evaluation result. */
export interface EngineEval {
  score_cp: number | null;
  score_display: string;
  mate_in: number | null;
  best_move: string;
  best_move_uci: string;
  pv: string[];
  pv_uci: string[];
  wdl: { win: number; draw: number; loss: number } | null;
  depth: number;
}

/** Critical moment from game narrative detection. */
export interface CriticalMoment {
  move_number: number;
  side: "white" | "black";
  san: string;
  fen_before: string;
  fen_after: string;
  eval_before_cp: number;
  eval_after_cp: number;
  delta_cp: number;
  classification: string;
  engine_best_move: string | null;
  key_lesson: string | null;
}

/** Narrative endpoint response. */
export interface NarrativeResponse {
  critical_moments: CriticalMoment[];
  count: number;
}

/** Tactical motif structure (simplified top-level). */
export interface TacticsResult {
  static: Record<string, unknown[]>;
  threats: Record<string, unknown[]>;
  sequences: Record<string, unknown[]>;
  opponent_threats?: Record<string, unknown[]>;
}

/** Full analysis result from /analyze endpoint. */
export interface AnalysisResult {
  fen: string;
  side_to_move: string;
  move_number: number;
  board_display: string;
  material: Record<string, unknown>;
  pawn_structure: Record<string, unknown>;
  piece_activity: Record<string, unknown>;
  files: Record<string, unknown>;
  king_safety: Record<string, unknown>;
  space: Record<string, unknown>;
  pins: unknown[];
  tactics: TacticsResult;
  development: Record<string, unknown>;
  game_phase: Record<string, unknown>;
  legal_moves: string[];
  is_check: boolean;
  is_checkmate: boolean;
  is_stalemate: boolean;
  superior_minor_piece?: Record<string, unknown>;
  initiative?: Record<string, unknown>;
  statics_vs_dynamics?: Record<string, unknown>;
  engine?: {
    available: boolean;
    eval: EngineEval | null;
    top_lines: EngineEval[] | null;
    depth: number | null;
  };
}
