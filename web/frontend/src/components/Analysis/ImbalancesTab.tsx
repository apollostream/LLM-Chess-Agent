/** Imbalances summary tab — human-readable summaries per imbalance. */

import type { AnalysisResult } from "../../api/types";

/* eslint-disable @typescript-eslint/no-explicit-any */

interface Props {
  analysis: AnalysisResult;
}

interface ImbalanceSummary {
  title: string;
  white: string;
  black: string;
  verdict: string;
}

function summarizeMaterial(data: any, phase: string): ImbalanceSummary {
  const w = data.white;
  const b = data.black;
  const bal = data.balance;
  const wBp = w.bishop_pair ? " (bishop pair)" : "";
  const bBp = b.bishop_pair ? " (bishop pair)" : "";

  let verdict: string;
  if (bal === 0) {
    verdict = "Material is equal.";
    if (w.bishop_pair && !b.bishop_pair) verdict = "Equal points, but White has the bishop pair.";
    if (b.bishop_pair && !w.bishop_pair) verdict = "Equal points, but Black has the bishop pair.";
  } else if (bal > 0) {
    verdict = `White is up ${Math.abs(bal)} point${Math.abs(bal) !== 1 ? "s" : ""}.`;
  } else {
    verdict = `Black is up ${Math.abs(bal)} point${Math.abs(bal) !== 1 ? "s" : ""}.`;
  }
  if (phase === "endgame" && bal !== 0) verdict += " Material advantages amplify in the endgame.";

  return {
    title: "Material",
    white: `${w.total_points} pts — ${w.pawns}P ${w.knights}N ${w.bishops}B ${w.rooks}R ${w.queens}Q${wBp}`,
    black: `${b.total_points} pts — ${b.pawns}P ${b.knights}N ${b.bishops}B ${b.rooks}R ${b.queens}Q${bBp}`,
    verdict,
  };
}

function summarizePawnStructure(data: any, phase: string): ImbalanceSummary {
  const descSide = (s: any): string => {
    const issues: string[] = [];
    if (s.doubled?.length) issues.push(`doubled on ${s.doubled.join(", ")}`);
    if (s.isolated?.length) issues.push(`isolated on ${s.isolated.join(", ")}`);
    if (s.backward?.length) issues.push(`backward on ${s.backward.join(", ")}`);
    if (s.passed?.length) issues.push(`passed on ${s.passed.join(", ")}`);
    if (issues.length === 0) return `${s.pawn_count} pawns, ${s.pawn_islands} island${s.pawn_islands !== 1 ? "s" : ""}, no weaknesses.`;
    return `${s.pawn_count} pawns, ${s.pawn_islands} island${s.pawn_islands !== 1 ? "s" : ""}: ${issues.join("; ")}.`;
  };

  const wIssues = (data.white.doubled?.length || 0) + (data.white.isolated?.length || 0) + (data.white.backward?.length || 0);
  const bIssues = (data.black.doubled?.length || 0) + (data.black.isolated?.length || 0) + (data.black.backward?.length || 0);
  const wPassed = data.white.passed?.length || 0;
  const bPassed = data.black.passed?.length || 0;

  let verdict = "Pawn structures are comparable.";
  if (wIssues > bIssues) verdict = "Black has the healthier pawn structure.";
  if (bIssues > wIssues) verdict = "White has the healthier pawn structure.";
  if (wPassed > bPassed) verdict += " White's passed pawn(s) are an asset.";
  if (bPassed > wPassed) verdict += " Black's passed pawn(s) are an asset.";
  if (phase === "endgame" && (wPassed || bPassed)) verdict += " Passed pawns are critical in the endgame.";

  return {
    title: "Pawn Structure",
    white: descSide(data.white),
    black: descSide(data.black),
    verdict,
  };
}

function summarizePieceActivity(data: any, phase: string): ImbalanceSummary {
  const descSide = (s: any): string => {
    const parts: string[] = [];
    parts.push(`${s.squares_attacked} squares attacked`);
    if (s.center_control?.length) parts.push(`controls ${s.center_control.join(", ")}`);
    if (s.knight_outposts?.length) parts.push(`outpost${s.knight_outposts.length > 1 ? "s" : ""} on ${s.knight_outposts.join(", ")}`);
    if (s.bishop_fianchetto?.length) parts.push(`fianchetto on ${s.bishop_fianchetto.join(", ")}`);
    if (s.rooks_on_open_files?.length) parts.push(`rook${s.rooks_on_open_files.length > 1 ? "s" : ""} on open file${s.rooks_on_open_files.length > 1 ? "s" : ""}`);
    if (s.rooks_on_7th_rank?.length) parts.push(`rook on 7th`);
    return parts.join("; ") + ".";
  };

  const wSq = data.white.squares_attacked || 0;
  const bSq = data.black.squares_attacked || 0;
  const diff = wSq - bSq;

  let verdict: string;
  if (Math.abs(diff) <= 3) verdict = "Piece activity is roughly equal.";
  else if (diff > 0) verdict = `White is more active (${diff} more squares).`;
  else verdict = `Black is more active (${-diff} more squares).`;
  if (phase === "opening") verdict += " Activity matters less until development completes.";

  return {
    title: "Piece Activity",
    white: descSide(data.white),
    black: descSide(data.black),
    verdict,
  };
}

function summarizeFiles(data: any): ImbalanceSummary {
  const open = data.open?.length ? `Open files: ${data.open.join(", ")}.` : "No open files.";
  const wSemi = data.white_semi_open?.length ? data.white_semi_open.join(", ") : "none";
  const bSemi = data.black_semi_open?.length ? data.black_semi_open.join(", ") : "none";

  let verdict = open;
  if (data.open?.length) verdict += " Both sides can contest these.";

  return {
    title: "Files",
    white: `Semi-open: ${wSemi}.`,
    black: `Semi-open: ${bSemi}.`,
    verdict,
  };
}

function summarizeKingSafety(data: any, phase: string): ImbalanceSummary {
  const descSide = (s: any): string => {
    const parts: string[] = [];
    if (s.likely_castled) parts.push("castled");
    else if (s.can_castle_kingside || s.can_castle_queenside) {
      const sides = [];
      if (s.can_castle_kingside) sides.push("K");
      if (s.can_castle_queenside) sides.push("Q");
      parts.push(`uncastled (can castle ${sides.join("/")})`);
    } else parts.push("cannot castle");

    const shield = s.pawn_shield?.length || 0;
    const missing = s.missing_shield?.length || 0;
    if (shield > 0 && missing === 0) parts.push("full pawn shield");
    else if (missing > 0) parts.push(`${missing} missing shield pawn${missing > 1 ? "s" : ""}`);

    if (s.nearby_attackers?.length) parts.push(`${s.nearby_attackers.length} nearby attacker${s.nearby_attackers.length > 1 ? "s" : ""}`);
    return parts.join("; ") + ".";
  };

  const wCastled = data.white.likely_castled;
  const bCastled = data.black.likely_castled;
  const wMissing = data.white.missing_shield?.length || 0;
  const bMissing = data.black.missing_shield?.length || 0;
  const wAttackers = data.white.nearby_attackers?.length || 0;
  const bAttackers = data.black.nearby_attackers?.length || 0;

  let verdict: string;
  if (wAttackers > bAttackers) verdict = "White's king is under more pressure.";
  else if (bAttackers > wAttackers) verdict = "Black's king is under more pressure.";
  else if (!wCastled && bCastled) verdict = "White hasn't castled yet — a concern.";
  else if (wCastled && !bCastled) verdict = "Black hasn't castled yet — a concern.";
  else if (wMissing > bMissing) verdict = "White's king shelter is weaker.";
  else if (bMissing > wMissing) verdict = "Black's king shelter is weaker.";
  else verdict = "King safety is comparable.";
  if (phase === "endgame") verdict += " Kings become active pieces in the endgame.";

  return {
    title: "King Safety",
    white: descSide(data.white),
    black: descSide(data.black),
    verdict,
  };
}

function summarizeSpace(data: any, phase: string): ImbalanceSummary {
  const wSq = data.white.squares_controlled_in_enemy_half || 0;
  const bSq = data.black.squares_controlled_in_enemy_half || 0;

  let verdict: string;
  const diff = wSq - bSq;
  if (Math.abs(diff) <= 1) verdict = "Space is balanced.";
  else if (diff > 0) verdict = `White controls more enemy territory (+${diff} squares).`;
  else verdict = `Black controls more enemy territory (+${-diff} squares).`;
  if (phase === "middlegame" && Math.abs(diff) >= 3) verdict += " A significant space edge restricts the opponent's pieces.";

  return {
    title: "Space",
    white: `${wSq} squares in Black's half (frontier rank ${data.white.pawn_frontier_rank}).`,
    black: `${bSq} squares in White's half (frontier rank ${data.black.pawn_frontier_rank}).`,
    verdict,
  };
}

function summarizeDevelopment(data: any, phase: string): ImbalanceSummary {
  const descSide = (s: any): string => {
    const remaining = s.total_developable - s.development_count;
    if (remaining === 0) return "Fully developed.";
    const undeveloped = s.pieces_on_starting_squares?.map((p: string) => p.split(" on ")[0]).join(", ") || "";
    return `${s.development_count}/${s.total_developable} developed${undeveloped ? ` (${undeveloped} still home)` : ""}.`;
  };

  const wDev = data.white.development_count / Math.max(data.white.total_developable, 1);
  const bDev = data.black.development_count / Math.max(data.black.total_developable, 1);

  let verdict: string;
  if (phase !== "opening") {
    verdict = "Development is less relevant in this phase.";
  } else if (Math.abs(wDev - bDev) < 0.1) {
    verdict = "Development is even.";
  } else if (wDev > bDev) {
    verdict = "White leads in development — should seek open play.";
  } else {
    verdict = "Black leads in development — should seek open play.";
  }

  return {
    title: "Development",
    white: descSide(data.white),
    black: descSide(data.black),
    verdict,
  };
}

function ImbalanceRow({ summary }: { summary: ImbalanceSummary }) {
  return (
    <div className="imb-row">
      <div className="imb-row-title">{summary.title}</div>
      <div className="imb-row-sides">
        <span className="imb-side"><strong>W:</strong> {summary.white}</span>
        <span className="imb-side"><strong>B:</strong> {summary.black}</span>
      </div>
      <div className="imb-row-verdict">{summary.verdict}</div>
    </div>
  );
}

export function ImbalancesTab({ analysis }: Props) {
  const phase = (analysis.game_phase as any)?.phase || "";

  const summaries: ImbalanceSummary[] = [
    summarizeMaterial(analysis.material, phase),
    summarizePawnStructure(analysis.pawn_structure, phase),
    summarizePieceActivity(analysis.piece_activity, phase),
    summarizeFiles(analysis.files),
    summarizeKingSafety(analysis.king_safety, phase),
    summarizeSpace(analysis.space, phase),
    summarizeDevelopment(analysis.development, phase),
  ];

  return (
    <div className="fade-in">
      <div className="imb-meta">
        {analysis.side_to_move} to move &middot; Move {analysis.move_number}
        {phase && <> &middot; {phase}</>}
      </div>
      {summaries.map((s) => (
        <ImbalanceRow key={s.title} summary={s} />
      ))}
      {analysis.pins.length > 0 && (
        <div className="imb-row">
          <div className="imb-row-title">Pins</div>
          <div className="imb-row-verdict">
            {analysis.pins.length} pin{analysis.pins.length > 1 ? "s" : ""} detected.
          </div>
        </div>
      )}
    </div>
  );
}
