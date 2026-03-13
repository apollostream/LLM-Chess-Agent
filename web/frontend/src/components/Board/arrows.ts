/**
 * Map tactical motifs to Chessground DrawShapes.
 *
 * All piece descriptions follow "piece on <square>" format.
 * Extract square: desc.split(" on ").pop()
 */

import type { DrawShape } from "chessground/draw";
import type { Key } from "chessground/types";

type Brush = "green" | "red" | "blue" | "yellow" | "paleGreen" | "paleRed" | "paleBlue";

function sq(desc: string): Key {
  return (desc.split(" on ").pop() ?? "") as Key;
}

function arrow(orig: Key, dest: Key, brush: Brush): DrawShape {
  return { orig, dest, brush };
}

function circle(key: Key, brush: Brush): DrawShape {
  return { orig: key, brush };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function tacticsToShapes(tactics: Record<string, any>): DrawShape[] {
  const shapes: DrawShape[] = [];

  // Static patterns
  const st = tactics.static ?? {};

  for (const pin of st.pins ?? []) {
    if (pin.pinner && pin.pinned_piece) {
      shapes.push(arrow(sq(pin.pinner), sq(pin.pinned_piece), "red"));
    }
    if (pin.pinned_piece && pin.pinned_to) {
      shapes.push(arrow(sq(pin.pinned_piece), sq(pin.pinned_to), "red"));
    }
  }

  for (const bat of st.batteries ?? []) {
    const pieces = bat.pieces ?? [];
    for (let i = 0; i < pieces.length - 1; i++) {
      shapes.push(arrow(sq(pieces[i]), sq(pieces[i + 1]), "blue"));
    }
  }

  for (const xray of st.xray_attacks ?? []) {
    if (xray.attacker && xray.through) {
      shapes.push(arrow(sq(xray.attacker), sq(xray.through), "paleBlue"));
    }
    if (xray.through && xray.target) {
      shapes.push(arrow(sq(xray.through), sq(xray.target), "paleBlue"));
    }
  }

  for (const hp of st.hanging_pieces ?? []) {
    if (hp.piece) shapes.push(circle(sq(hp.piece), "red"));
  }

  for (const tp of st.trapped_pieces ?? []) {
    if (tp.piece) shapes.push(circle(sq(tp.piece), "paleRed"));
  }

  for (const pp of st.advanced_passed_pawns ?? []) {
    if (pp.pawn) shapes.push(circle(sq(pp.pawn), "green"));
  }

  // Threats
  const th = tactics.threats ?? {};

  for (const fork of th.forks ?? []) {
    if (fork.landing_square) {
      const landing = fork.landing_square as Key;
      shapes.push(circle(landing, "yellow"));
      for (const target of fork.targets ?? []) {
        shapes.push(arrow(landing, sq(target), "yellow"));
      }
    }
  }

  for (const skewer of th.skewers ?? []) {
    if (skewer.move_to && skewer.front_target) {
      shapes.push(arrow(skewer.move_to as Key, sq(skewer.front_target), "green"));
    }
    if (skewer.front_target && skewer.rear_target) {
      shapes.push(arrow(sq(skewer.front_target), sq(skewer.rear_target), "green"));
    }
  }

  for (const da of th.discovered_attacks ?? []) {
    if (da.revealed_attacker && da.target) {
      shapes.push(arrow(sq(da.revealed_attacker), sq(da.target), "blue"));
    }
  }

  for (const dc of th.discovered_checks ?? []) {
    if (dc.revealed_attacker && dc.target) {
      shapes.push(arrow(sq(dc.revealed_attacker), sq(dc.target), "blue"));
    }
  }

  for (const brm of th.back_rank_mates ?? []) {
    if (brm.attacking_piece && brm.mate_square) {
      shapes.push(arrow(sq(brm.attacking_piece), brm.mate_square as Key, "red"));
    }
  }

  return shapes;
}
