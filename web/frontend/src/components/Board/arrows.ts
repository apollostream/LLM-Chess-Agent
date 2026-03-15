/**
 * Map tactical motifs to Chessground DrawShapes.
 *
 * All piece descriptions follow "piece on <square>" format.
 * Extract square: desc.split(" on ").pop()
 *
 * Shapes are tagged with category ("static" | "threat") and side ("white" | "black")
 * to support per-side next-move toggle in the UI.
 */

import type { DrawShape } from "chessground/draw";
import type { Key } from "chessground/types";

type Brush = "green" | "red" | "blue" | "yellow" | "paleGreen" | "paleRed" | "paleBlue";
type Category = "static" | "threat";
type Side = "white" | "black" | "neutral";

export interface TaggedShape {
  shape: DrawShape;
  category: Category;
  side: Side;
}

function sq(desc: string): Key {
  return (desc.split(" on ").pop() ?? "") as Key;
}

function arrow(orig: Key, dest: Key, brush: Brush): DrawShape {
  return { orig, dest, brush };
}

function circle(key: Key, brush: Brush): DrawShape {
  return { orig: key, brush };
}

/* eslint-disable @typescript-eslint/no-explicit-any */

/** Build shapes for a checkmate position — only the mating pattern. */
export function checkmateDiagramShapes(diagram: Record<string, any>): DrawShape[] {
  const shapes: DrawShape[] = [];
  const kingSquare = diagram.king_square as Key;

  // Red circle on the mated king
  shapes.push(circle(kingSquare, "red"));

  // Red arrows from checking pieces to the king
  for (const checker of diagram.checkers ?? []) {
    shapes.push(arrow(checker.square as Key, kingSquare, "red"));
  }

  // Blocked escape squares
  for (const b of diagram.blocked_squares ?? []) {
    if (b.reason === "attacked" && b.attacker_square) {
      // Arrow from attacker to the escape square it covers
      shapes.push(arrow(b.attacker_square as Key, b.square as Key, "paleRed"));
    } else if (b.reason === "own_piece") {
      // Circle on own piece blocking escape
      shapes.push(circle(b.square as Key, "paleBlue"));
    }
  }

  return shapes;
}

export function tacticsToTaggedShapes(tactics: Record<string, any>): TaggedShape[] {
  const tagged: TaggedShape[] = [];

  const push = (shape: DrawShape, category: Category, side: Side) =>
    tagged.push({ shape, category, side });

  // ── Static patterns (current-move) ──────────────────────────────────

  const st = tactics.static ?? {};

  for (const pin of st.pins ?? []) {
    const side = (pin.side ?? "neutral") as Side;
    if (pin.pinner && pin.pinned_piece) {
      push(arrow(sq(pin.pinner), sq(pin.pinned_piece), "red"), "static", side);
    }
    if (pin.pinned_piece && pin.pinned_to) {
      push(arrow(sq(pin.pinned_piece), sq(pin.pinned_to), "red"), "static", side);
    }
  }

  for (const bat of st.batteries ?? []) {
    const side = (bat.side ?? "neutral") as Side;
    const pieces = bat.pieces ?? [];
    for (let i = 0; i < pieces.length - 1; i++) {
      push(arrow(sq(pieces[i]), sq(pieces[i + 1]), "blue"), "static", side);
    }
  }

  for (const xray of st.xray_attacks ?? []) {
    const side = (xray.side ?? "neutral") as Side;
    if (xray.attacker && xray.through) {
      push(arrow(sq(xray.attacker), sq(xray.through), "paleBlue"), "static", side);
    }
    if (xray.through && xray.target) {
      push(arrow(sq(xray.through), sq(xray.target), "paleBlue"), "static", side);
    }
  }

  for (const hp of st.hanging_pieces ?? []) {
    const side = (hp.side ?? "neutral") as Side;
    if (hp.piece) push(circle(sq(hp.piece), "red"), "static", side);
  }

  for (const tp of st.trapped_pieces ?? []) {
    const side = (tp.side ?? "neutral") as Side;
    if (tp.piece) push(circle(sq(tp.piece), "paleRed"), "static", side);
  }

  for (const pp of st.advanced_passed_pawns ?? []) {
    const side = (pp.side ?? "neutral") as Side;
    if (pp.square) push(circle(pp.square as Key, "green"), "static", side);
  }

  // ── Threats (next-move) ─────────────────────────────────────────────

  const th = tactics.threats ?? {};

  for (const fork of th.forks ?? []) {
    const side = (fork.side ?? "neutral") as Side;
    if (fork.landing_square) {
      const landing = fork.landing_square as Key;
      push(circle(landing, "yellow"), "threat", side);
      for (const target of fork.targets ?? []) {
        push(arrow(landing, sq(target), "yellow"), "threat", side);
      }
    }
  }

  for (const skewer of th.skewers ?? []) {
    const side = (skewer.side ?? "neutral") as Side;
    if (skewer.move_to && skewer.front_target) {
      push(arrow(skewer.move_to as Key, sq(skewer.front_target), "green"), "threat", side);
    }
    if (skewer.front_target && skewer.rear_target) {
      push(arrow(sq(skewer.front_target), sq(skewer.rear_target), "green"), "threat", side);
    }
  }

  for (const da of th.discovered_attacks ?? []) {
    const side = (da.side ?? "neutral") as Side;
    if (da.revealed_attacker && da.target) {
      push(arrow(sq(da.revealed_attacker), sq(da.target), "blue"), "threat", side);
    }
  }

  for (const dc of th.discovered_checks ?? []) {
    const side = (dc.side ?? "neutral") as Side;
    if (dc.revealed_attacker && dc.target) {
      push(arrow(sq(dc.revealed_attacker), sq(dc.target), "blue"), "threat", side);
    }
  }

  for (const cm of th.checkmate_threats ?? []) {
    const side = (cm.side ?? "neutral") as Side;
    if (cm.attacking_piece && cm.mate_square) {
      push(arrow(sq(cm.attacking_piece), cm.mate_square as Key, "red"), "threat", side);
    }
  }

  for (const brm of th.back_rank_mates ?? []) {
    const side = (brm.side ?? "neutral") as Side;
    if (brm.attacking_piece && brm.mate_square) {
      push(arrow(sq(brm.attacking_piece), brm.mate_square as Key, "red"), "threat", side);
    }
  }

  for (const rog of th.removal_of_guard ?? []) {
    const side = (rog.side ?? "neutral") as Side;
    if (rog.captured_guard && rog.exposed_piece) {
      push(arrow(sq(rog.captured_guard), sq(rog.exposed_piece), "paleRed"), "threat", side);
    }
  }

  // ── Opponent threats (next-move, from opponent's perspective) ───────

  const opp = tactics.opponent_threats ?? {};

  for (const cm of opp.checkmate_threats ?? []) {
    const side = (cm.side ?? "neutral") as Side;
    if (cm.attacking_piece && cm.mate_square) {
      push(arrow(sq(cm.attacking_piece), cm.mate_square as Key, "paleRed"), "threat", side);
    }
  }

  for (const brm of opp.back_rank_mates ?? []) {
    const side = (brm.side ?? "neutral") as Side;
    if (brm.attacking_piece && brm.mate_square) {
      push(arrow(sq(brm.attacking_piece), brm.mate_square as Key, "paleRed"), "threat", side);
    }
  }

  for (const fork of opp.forks ?? []) {
    const side = (fork.side ?? "neutral") as Side;
    if (fork.landing_square) {
      const landing = fork.landing_square as Key;
      push(circle(landing, "paleRed"), "threat", side);
      for (const target of fork.targets ?? []) {
        push(arrow(landing, sq(target), "paleRed"), "threat", side);
      }
    }
  }

  for (const da of opp.discovered_attacks ?? []) {
    const side = (da.side ?? "neutral") as Side;
    if (da.revealed_attacker && da.target) {
      push(arrow(sq(da.revealed_attacker), sq(da.target), "paleBlue"), "threat", side);
    }
  }

  for (const dc of opp.discovered_checks ?? []) {
    const side = (dc.side ?? "neutral") as Side;
    if (dc.revealed_attacker && dc.target) {
      push(arrow(sq(dc.revealed_attacker), sq(dc.target), "paleBlue"), "threat", side);
    }
  }

  return tagged;
}

/** Filter tagged shapes and return plain DrawShapes for Chessground. */
export function filterShapes(
  tagged: TaggedShape[],
  showWhiteThreats: boolean,
  showBlackThreats: boolean,
): DrawShape[] {
  return tagged
    .filter((t) => {
      if (t.category === "static") return true;
      // threat category — filter by side
      if (t.side === "white") return showWhiteThreats;
      if (t.side === "black") return showBlackThreats;
      // neutral threats: show if either toggle is on
      return showWhiteThreats || showBlackThreats;
    })
    .map((t) => t.shape);
}
