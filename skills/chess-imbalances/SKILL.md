---
name: chess-imbalances
description: >
  Analyze chess positions using Silman's imbalance framework.
  Triggers on: FEN strings, PGN content, chess position analysis requests,
  "assess imbalances", "evaluate position", "what should White/Black do",
  "analyze this position". Append --deep for full BFIH treatment.
---

# Chess Imbalances Analysis Skill

Analyze any chess position through Jeremy Silman's 10-imbalance framework from *Reassess Your Chess*. Produces structured strategic assessments that identify who stands better, why, and what plans follow.

## Two Modes

- **Default mode:** Systematic imbalance catalog + strategic narrative. Fast, practical, covers all 10 categories.
- **Deep mode** (triggered by `--deep`): Full BFIH protocol — competing hypotheses, paradigm inversion, evidence matrix, reflexive review. For positions with genuine strategic tension where the "obvious" assessment might be wrong.

## Input Handling

Accept any of these formats — auto-detect:

| Input | Example | Detection |
|-------|---------|-----------|
| FEN string | `rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1` | Contains `/` characters |
| PGN file | `game.pgn` | File path ending in `.pgn` |
| Move list | `1. e4 e5 2. Nf3 Nc6 3. Bb5` | SAN moves with or without numbers |
| Verbal | "Ruy Lopez after 6...d6" | Set up the position from known opening theory |

For verbal descriptions, set up the position using known opening theory, then generate the FEN before analysis.

## Default Mode Workflow

Follow Silman's 5-step assessment technique, mapped to concrete actions:

### Step 1: Get the Data

Run the position through `board_utils.py` to get structured JSON:

```bash
skills/chess-imbalances/scripts/parse_position.sh "<FEN_OR_INPUT>" --format json
```

If the script is unavailable or fails, analyze the position directly from the FEN using your chess knowledge — the script is a tool, not a requirement.

### Step 2: Scan All 10 Imbalances

Check every category systematically. Reference `references/imbalances_guide.md` for detailed guidance on each:

| # | Imbalance | Key JSON Fields | What Claude Adds |
|---|-----------|----------------|-----------------|
| 1 | Superior Minor Piece | `material.*bishop_pair`, `piece_activity.*knight_outposts`, `pawn_structure` | Open vs closed assessment, piece quality judgment |
| 2 | Pawn Structure | `pawn_structure.*` | Structural narrative, weakness severity, dynamic compensation |
| 3 | Space | `space.*` | Whether space advantage is exploitable or overextended |
| 4 | Material | `material.*` | Quality assessment beyond point count |
| 5 | Control of Key File | `files.*`, `piece_activity.*rooks_on_*` | Whether file control leads to penetration |
| 6 | Hole / Weak Square | `piece_activity.*knight_outposts` | Color complex analysis, potential outpost identification |
| 7 | Lead in Development | `development.*`, `king_safety.*can_castle*` | Whether the lead matters given position type |
| 8 | Initiative | `is_check`, `legal_moves`, activity metrics | Threat assessment, forcing move identification |
| 9 | King Safety | `king_safety.*` | Attack potential assessment, pawn storm possibilities |
| 10 | Statics vs Dynamics | `game_phase`, all fields | Meta-assessment: which imbalances matter NOW |

### Step 3: Identify Who Benefits

For each relevant imbalance, determine which side benefits and by how much. Not all imbalances matter equally — the position type (static vs dynamic, open vs closed) determines which ones dominate.

### Step 4: Synthesize

Weigh the imbalances against each other. A strong passed pawn might outweigh a slight space disadvantage. A development lead might be irrelevant in a closed position. Produce a unified assessment.

### Step 5: Form a Plan

Based on the imbalances, identify:
- **Target sector:** Where should the advantaged side play? (Kingside, queenside, center)
- **Fantasy position:** What ideal piece placement would maximize the advantages?
- **Candidate moves:** 3-5 concrete moves that work toward the plan

## Deep Mode Workflow

When the user appends `--deep` or asks for deep analysis:

1. Read `references/bfih_chess_protocol.md` for the full protocol
2. Follow all 5 phases: K₀ declaration → Hypothesis generation → Ontological scan → Evidence matrix → Reflexive review → Synthesis
3. The paradigm inversion is non-negotiable — genuinely argue the opposite position
4. Apply the discomfort heuristic as a final quality check

## Output Format — Default Mode

```markdown
## Position Analysis

### Board
[Unicode board display from board_utils or rendered from FEN]

### Position Summary
[1-2 sentence high-level assessment — who stands better, why, game phase]

### White's Imbalances
- **[Imbalance Name]**: [Specific details — name squares, pieces, concrete features]
  [Brief note on significance]

### Black's Imbalances
- **[Imbalance Name]**: [Specific details]
  [Brief note on significance]

### Synthesis
[Narrative weighing all imbalances — who stands better, why, how much.
 Reference the most critical imbalances by name. Note any tensions or
 compensating factors. State whether the advantage is static or dynamic.]

### Plan Direction
- **Target sector**: [Kingside / Queenside / Center — and why]
- **Fantasy position**: [Ideal piece placement in 1-2 sentences]
- **Candidate moves**: [3-5 moves with strategic rationale tied to imbalances]
```

## Output Format — Deep Mode

Extends default mode with the full BFIH protocol output. See `references/bfih_chess_protocol.md` for the complete template. Key additions:

- K₀ statement with explicit priors and disconfirming triggers
- 2-4 competing hypotheses with probability assignments
- Full 10-category ontological scan
- Ancestral check (structural analogies, paradigm precedents)
- Paradigm inversion (forced counter-argument)
- Evidence matrix mapping imbalances to hypotheses
- Updated posteriors with reasoning
- Reflexive review with red team argument
- Synthesis with confidence levels and disconfirming evidence acknowledged

## Resource Pointers

| Resource | When to Read |
|----------|-------------|
| `references/imbalances_guide.md` | When you need detailed guidance on any of the 10 imbalances — what to look for, how to weigh it, common errors |
| `references/bfih_chess_protocol.md` | When running deep mode — follow the full protocol step by step |
| `scripts/board_utils.py` | Don't read the source unless debugging — just run it via `parse_position.sh` |

## Dependencies

- Python 3.10+ with `python-chess` installed in project `.venv`
- Run `scripts/install_deps.sh` if dependencies are missing

## Notes

- The script's analysis is a starting point, not an endpoint. Claude's chess knowledge should supplement and contextualize the raw data.
- Not all 10 imbalances will be relevant in every position. Focus on the 2-4 that define the position's character.
- When imbalances conflict (e.g., material advantage vs king safety deficit), the synthesis must address the tension explicitly.
- This skill produces strategic assessments, not engine-style evaluations. The goal is understanding, not a centipawn score.
