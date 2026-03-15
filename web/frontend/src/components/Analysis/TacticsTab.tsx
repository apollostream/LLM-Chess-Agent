/** Tactics display tab — human-readable summaries per motif. */

import type { TacticsResult } from "../../api/types";

/* eslint-disable @typescript-eslint/no-explicit-any */

// ── Piece description helpers ──────────────────────────────────────────────

/** "knight on f3" → "Nf3" */
function shortPiece(desc: string): string {
  const m = desc.match(/^(\w+)\s+on\s+([a-h][1-8])$/);
  if (!m) return desc;
  const piece = m[1].toLowerCase();
  const sq = m[2];
  const symbol: Record<string, string> = {
    pawn: "", knight: "N", bishop: "B", rook: "R", queen: "Q", king: "K",
  };
  return `${symbol[piece] ?? piece[0].toUpperCase()}${sq}`;
}

function sideLabel(side: string): string {
  return side === "white" ? "White" : "Black";
}

// ── Static pattern summarizers ─────────────────────────────────────────────

function describePin(p: any): string {
  const type = p.pin_type === "absolute" ? "Absolute" : "Relative";
  return `${type} pin: ${shortPiece(p.pinner)} pins ${shortPiece(p.pinned_piece)} to ${shortPiece(p.pinned_to)} (${sideLabel(p.pinned_side)}'s piece pinned).`;
}

function describeBattery(b: any): string {
  const pieces = (b.pieces as string[]).map(shortPiece).join(" + ");
  return `${sideLabel(b.side)} battery on ${b.line}: ${pieces}.`;
}

function describeXray(x: any): string {
  return `${sideLabel(x.side)} x-ray: ${shortPiece(x.attacker)} through ${shortPiece(x.through)} at ${shortPiece(x.target)}.`;
}

function describeHanging(h: any): string {
  const kind = h.type === "undefended" ? "undefended" : "underdefended";
  return `${shortPiece(h.piece)} is ${kind} on ${h.square}.`;
}

function describeOverloaded(o: any): string {
  const guarding = (o.guarding as string[]).map(shortPiece).join(", ");
  return `${shortPiece(o.piece)} is overloaded — guarding ${guarding}.`;
}

function describeTrapped(t: any): string {
  return `${shortPiece(t.piece)} is trapped on ${t.square} (no safe squares).`;
}

function describeAdvancedPasser(p: any): string {
  const prot = p.is_protected ? "protected" : "unprotected";
  return `${sideLabel(p.side)} ${prot} passed pawn on ${p.square} (rank ${p.rank}).`;
}

function describeAlignment(a: any): string {
  const pieces = (a.pieces as string[]).map(shortPiece).join(" and ");
  return `${pieces} aligned on ${a.line} — potential ${a.potential}.`;
}

function describeWeakBackRank(data: any): string[] {
  const lines: string[] = [];
  for (const side of ["white", "black"]) {
    const s = data[side];
    if (!s) continue;
    if (s.is_weak) {
      lines.push(`${sideLabel(side)}'s back rank is weak (${s.escape_squares.length} escape square${s.escape_squares.length !== 1 ? "s" : ""}).`);
    }
  }
  return lines;
}

// ── Threat summarizers ─────────────────────────────────────────────────────

function describeFork(f: any): string {
  const targets = (f.targets as string[]).map(shortPiece).join(" and ");
  return `${sideLabel(f.side)} fork: ${f.move} attacks ${targets}.`;
}

function describeSkewer(s: any): string {
  return `${sideLabel(s.side)} skewer: ${s.move} — ${shortPiece(s.front_target)} in front of ${shortPiece(s.rear_target)}.`;
}

function describeDiscoveredAttack(d: any): string {
  return `${sideLabel(d.side)} discovered attack: ${d.move} reveals ${shortPiece(d.revealed_attacker)} on ${shortPiece(d.target)}.`;
}

function describeDiscoveredCheck(d: any): string {
  return `${sideLabel(d.side)} discovered check: ${d.move} reveals ${shortPiece(d.checking_piece)}.`;
}

function describeDoubleCheck(d: any): string {
  const checkers = (d.checkers as string[]).map(shortPiece).join(" and ");
  return `${sideLabel(d.side)} double check: ${d.move} with ${checkers}.`;
}

function describeCheckmateThreat(c: any): string {
  return `${sideLabel(c.side)} CHECKMATE: ${c.move} on ${c.mate_square}.`;
}

function describeBackRankMate(b: any): string {
  return `${sideLabel(b.side)} back rank mate: ${b.move}#!`;
}

function describeRemovalOfGuard(r: any): string {
  return `${sideLabel(r.side)}: ${r.move} captures ${shortPiece(r.captured_guard)}, exposing ${shortPiece(r.exposed_piece)}.`;
}

// ── Sequence summarizers ───────────────────────────────────────────────────

function describeDeflection(d: any): string {
  return `${sideLabel(d.side)} deflection: ${d.forcing_move} forces ${shortPiece(d.target_piece)} away — ${d.followup}.`;
}

function describeZwischenzug(z: any): string {
  return `Zwischenzug: instead of recapture (${z.expected_recapture}), ${z.zwischenzug_move} first.`;
}

function describeSmotheredMate(s: any): string {
  if (s.sequence) {
    return `${sideLabel(s.side)} smothered mate: ${(s.sequence as string[]).join(", ")}.`;
  }
  return `${sideLabel(s.side)} smothered mate: ${s.move}#.`;
}

// ── Mapping motif keys to summarizers ──────────────────────────────────────

type Summarizer = (item: any) => string;
type SpecialSummarizer = (data: any) => string[];

interface MotifConfig {
  label: string;
  icon: string;
  summarize?: Summarizer;
  special?: SpecialSummarizer;
}

const STATIC_MOTIFS: Record<string, MotifConfig> = {
  pins: { label: "Pins", icon: "📌", summarize: describePin },
  batteries: { label: "Batteries", icon: "⚡", summarize: describeBattery },
  xray_attacks: { label: "X-ray Attacks", icon: "🔭", summarize: describeXray },
  hanging_pieces: { label: "Hanging Pieces", icon: "⚠️", summarize: describeHanging },
  overloaded_pieces: { label: "Overloaded Pieces", icon: "🏋️", summarize: describeOverloaded },
  weak_back_rank: { label: "Weak Back Rank", icon: "🏰", special: describeWeakBackRank },
  trapped_pieces: { label: "Trapped Pieces", icon: "🪤", summarize: describeTrapped },
  advanced_passed_pawns: { label: "Advanced Passed Pawns", icon: "⬆️", summarize: describeAdvancedPasser },
  alignments: { label: "Alignments", icon: "🎯", summarize: describeAlignment },
};

const THREAT_MOTIFS: Record<string, MotifConfig> = {
  checkmate_threats: { label: "Checkmate", icon: "👑", summarize: describeCheckmateThreat },
  forks: { label: "Forks", icon: "🍴", summarize: describeFork },
  skewers: { label: "Skewers", icon: "🗡️", summarize: describeSkewer },
  discovered_attacks: { label: "Discovered Attacks", icon: "💥", summarize: describeDiscoveredAttack },
  discovered_checks: { label: "Discovered Checks", icon: "⚡", summarize: describeDiscoveredCheck },
  double_checks: { label: "Double Checks", icon: "✨", summarize: describeDoubleCheck },
  back_rank_mates: { label: "Back Rank Mates", icon: "💀", summarize: describeBackRankMate },
  removal_of_guard: { label: "Removal of Guard", icon: "🛡️", summarize: describeRemovalOfGuard },
};

const SEQUENCE_MOTIFS: Record<string, MotifConfig> = {
  deflections: { label: "Deflections", icon: "↗️", summarize: describeDeflection },
  zwischenzug: { label: "Zwischenzug", icon: "⏸️", summarize: describeZwischenzug },
  smothered_mates: { label: "Smothered Mates", icon: "♞", summarize: describeSmotheredMate },
};

const OPPONENT_THREAT_MOTIFS: Record<string, MotifConfig> = {
  checkmate_threats: { label: "Checkmate Threats", icon: "👑", summarize: describeCheckmateThreat },
  back_rank_mates: { label: "Back Rank Mate Threats", icon: "💀", summarize: describeBackRankMate },
  forks: { label: "Fork Threats", icon: "🍴", summarize: describeFork },
  discovered_attacks: { label: "Discovered Attack Threats", icon: "💥", summarize: describeDiscoveredAttack },
  discovered_checks: { label: "Discovered Check Threats", icon: "⚡", summarize: describeDiscoveredCheck },
};

// ── Components ─────────────────────────────────────────────────────────────

function MotifSection({ data, config }: { data: any; config: MotifConfig }) {
  // Special handler (weak_back_rank returns a dict, not a list)
  if (config.special) {
    const lines = config.special(data);
    if (lines.length === 0) return null;
    return (
      <div className="imb-row">
        <div className="imb-row-title">{config.icon} {config.label}</div>
        {lines.map((line, i) => (
          <div key={i} className="imb-row-verdict">{line}</div>
        ))}
      </div>
    );
  }

  // Normal list-based motifs
  if (!Array.isArray(data) || data.length === 0) return null;
  const summarize = config.summarize!;

  return (
    <div className="imb-row">
      <div className="imb-row-title">
        {config.icon} {config.label}
        <span style={{ opacity: 0.5, marginLeft: 6 }}>({data.length})</span>
      </div>
      {data.map((item: any, i: number) => (
        <div key={i} className="imb-row-verdict">{summarize(item)}</div>
      ))}
    </div>
  );
}

function TierBlock({ title, tier, motifs }: {
  title: string;
  tier: Record<string, any>;
  motifs: Record<string, MotifConfig>;
}) {
  const active = Object.entries(motifs).filter(([key]) => {
    const data = tier[key];
    if (!data) return false;
    if (Array.isArray(data)) return data.length > 0;
    // Special case: weak_back_rank is a dict
    if (typeof data === "object") {
      return Object.values(data).some((s: any) => s?.is_weak);
    }
    return false;
  });

  if (active.length === 0) return null;

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-tertiary)", marginBottom: 4 }}>
        {title}
      </div>
      {active.map(([key, config]) => (
        <MotifSection key={key} data={tier[key]} config={config} />
      ))}
    </div>
  );
}

export function TacticsTab({ tactics }: { tactics: TacticsResult }) {
  const hasAny = [tactics.static, tactics.threats, tactics.sequences, tactics.opponent_threats].some(
    (tier) => tier && Object.values(tier).some((v) => {
      if (Array.isArray(v)) return v.length > 0;
      if (typeof v === "object" && v !== null) return Object.values(v).some((s: any) => s?.is_weak);
      return false;
    }),
  );

  if (!hasAny) {
    return <div className="tactics-empty fade-in">No tactical motifs detected.</div>;
  }

  return (
    <div className="fade-in">
      <TierBlock title="Static Patterns" tier={tactics.static as Record<string, any>} motifs={STATIC_MOTIFS} />
      <TierBlock title="Single-Move Threats" tier={tactics.threats as Record<string, any>} motifs={THREAT_MOTIFS} />
      <TierBlock title="Forced Sequences" tier={tactics.sequences as Record<string, any>} motifs={SEQUENCE_MOTIFS} />
      {tactics.opponent_threats && (
        <TierBlock title="Opponent Threats" tier={tactics.opponent_threats as Record<string, any>} motifs={OPPONENT_THREAT_MOTIFS} />
      )}
    </div>
  );
}
