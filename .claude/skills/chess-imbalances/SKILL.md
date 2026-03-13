---
name: chess-imbalances
description: >
  Analyze chess positions using Silman's imbalance framework.
  Triggers on: FEN strings, PGN content, chess position analysis requests,
  "assess imbalances", "evaluate position", "what should White/Black do",
  "analyze this position". Append --deep for full BFIH treatment.
  Append --no-save to skip file output.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Chess Imbalances Analysis Skill

Analyze any chess position through Jeremy Silman's 10-imbalance framework from *Reassess Your Chess*. Produces structured strategic assessments that identify who stands better, why, and what plans follow.

## Modes and Flags

- **Default mode:** Systematic imbalance catalog + strategic narrative. Fast, practical, covers all 10 categories.
- **Deep mode** (triggered by `--deep`): Full BFIH protocol — competing hypotheses, paradigm inversion, evidence matrix, reflexive review. For positions with genuine strategic tension where the "obvious" assessment might be wrong.
- **Narrative mode** (triggered by `--narrative`): Full-game analysis — engine sweep for critical moments, arc classification, game story. Requires a PGN file as input.
- **`--no-save`**: Skip file output; print the full analysis to the console only.
- **`--save`** (default): Write the full analysis to a markdown file and print a concise summary to the console.
- **`--engine`**: Enable Stockfish engine evaluation (requires Stockfish installed). Adds eval, best move, PV, WDL%, and top N lines.
- **`--depth N`**: Engine search depth (default: 20). Higher = stronger but slower.
- **`--lines N`**: Number of multi-PV lines to display (default: 3).

## Input Handling

Accept any of these formats — auto-detect:

| Input | Example | Detection |
|-------|---------|-----------|
| FEN string | `rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1` | Contains `/` characters |
| PGN file | `game.pgn` | File path ending in `.pgn` |
| Move list | `1. e4 e5 2. Nf3 Nc6 3. Bb5` | SAN moves with or without numbers |
| Verbal | "Ruy Lopez after 6...d6" | Set up the position from known opening theory |

For verbal descriptions, set up the position using known opening theory, then generate the FEN before analysis.

### Move targeting (`--move`)

For PGN files and move lists, you can analyze a specific move instead of the final position:

```bash
parse_position.sh game.pgn --move 15        # Position after White's 15th move
parse_position.sh game.pgn --move 15b       # Position after Black's 15th move
parse_position.sh "1. e4 e5 2. Nf3" --move 1   # Position after 1. e4
```

Ignored for FEN input (FEN already specifies a position).

## Default Mode Workflow

Follow Silman's 5-step assessment technique, mapped to concrete actions:

### Step 1: Get the Data

Run the position through `board_utils.py` to get structured JSON:

```bash
.claude/skills/chess-imbalances/scripts/parse_position.sh "<FEN_OR_INPUT>" --format json
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
| 8 | Initiative | `is_check`, `legal_moves`, activity metrics, `tactics.threats.*`, `tactics.sequences.*` | Threat assessment, forcing move identification, concrete tactical resources |
| 9 | King Safety | `king_safety.*`, `tactics.static.weak_back_rank`, `tactics.threats.back_rank_mates` | Attack potential assessment, pawn storm possibilities, back rank vulnerability |
| 10 | Statics vs Dynamics | `game_phase`, all fields, `tactics.static.*` vs `tactics.threats.*` | Meta-assessment: which imbalances matter NOW, static features vs concrete threats |

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

When the user appends `--deep` or asks for deep analysis, follow this enforced per-phase protocol. Each phase produces validated JSON before proceeding to the next. Read `references/bfih_chess_protocol.md` for conceptual guidance; the steps below are the actionable protocol.

### Step 0: Position Data

Run `parse_position.sh` and save the output:

```bash
.claude/skills/chess-imbalances/scripts/parse_position.sh "<FEN_OR_INPUT>" --format json --engine --depth 20 --lines 3 > analysis/bfih_phases/position_data.json
```

If Stockfish is unavailable the `--engine` flag is silently ignored and the `engine` key will be absent from the output. The analysis proceeds without engine data.

Create the `analysis/bfih_phases/` directory if it doesn't exist.

### Steps 1–9: Per-Phase Protocol

For **each phase** (1 through 9):

1. **Generate**: Reason through the phase using the position data and any prior phases. Produce JSON matching the phase schema.
2. **Write**: Save to `analysis/bfih_phases/phase_N.json`
3. **Validate**: Run the validator:
   ```bash
   .venv/bin/python .claude/skills/chess-imbalances/scripts/bfih_validator.py validate-phase N analysis/bfih_phases/phase_N.json --prior-phases analysis/bfih_phases/
   ```
   For Phase 8, add `--position-data analysis/bfih_phases/position_data.json` to check candidate move legality (gate G8).
4. **If validation fails**: Read the error, fix the JSON, rewrite, and re-validate (max 2 retries).
5. **If 3 failures**: Note the degradation in the output, continue to the next phase.

To see the JSON schema for any phase: `.venv/bin/python .claude/skills/chess-imbalances/scripts/bfih_validator.py schema N`

#### Phase Details

| Phase | Model | Key Constraints | Cross-Phase Gate |
|-------|-------|----------------|-----------------|
| 1 | K0 | `opening_context` ≥10 chars, `gut_read` ≥20, 2-4 disconfirming triggers (each ≥15 chars) | — |
| 2 | HypothesisSet | 2-5 hypotheses, priors sum to 1.0±0.01, H_catch required, IDs unique | **G2**: ≥1 hypothesis differs from K0 direction |
| 3 | OntologicalScan | Exactly 10 findings (numbers 1-10), each `finding` ≥10 chars | — |
| 4 | AncestralCheck | `structural_analogy` ≥20, `paradigm_precedent` ≥20 | — |
| 5 | ParadigmInversion | `inverted_argument` ≥80 chars, `new_considerations` ≥1 | **G5**: `inverted_assessment` must differ in direction from K0 |
| 6 | EvidenceMatrix | ≥3 evidence rows, posteriors sum to 1.0±0.01, `reasoning` ≥20 | **G6**: ≥1 posterior moved >0.05 from prior |
| 7 | ReflexiveReview | `red_team_argument` ≥40 chars | — |
| 8 | Synthesis | 3-5 candidate moves with rationale ≥10, 1-4 key imbalances, `k0_revision` ≥20, `position_narrative` ≥40 (2nd person coach voice), `key_takeaway` ≥20 (chess lesson to internalize) | **G8**: All candidate moves must be legal |
| 9 | DiscomfortHeuristic | Auto-warns if `feels_comfortable=true` AND `more_uncertain_than_start=false` | — |

#### Quality Gate: Paradigm Inversion (Phase 5)

The inversion is **rejected** if `felt_easy_to_dismiss=true` AND `abs(probability_shift) < 0.05`. This catches straw-man inversions. If rejected, genuinely argue the opposite before continuing.

#### Pre-Population Notes

- **Phase 3** (Ontological Scan): Use raw findings from `position_data.json` — the 10 imbalance categories map to JSON sections per the default mode table.
- **Phase 5** (Paradigm Inversion): If engine data is available in `position_data.json["engine"]`, use the engine evaluation to stress-test or support the inverted argument. If the engine disagrees with K0, that's evidence the inversion has teeth. If the engine agrees with K0, the inversion must argue why strategic factors the engine underweights (long-term pawn structure, piece coordination, prophylaxis) could matter more.
- **Phase 6** (Evidence Matrix): Use hypothesis IDs from Phase 2; map ontological findings to hypotheses using likelihood ratings (++, +, 0, -, --). If engine data is available, include at least one evidence row referencing the engine's evaluation (e.g., "Engine scores position +0.32 for White") and rate it against each hypothesis.
- **Phase 8** (Synthesis): Candidate moves must be from `position_data.json["legal_moves"]`. **Engine cross-reference is required when engine data is available:**
  1. Read `position_data.json["engine"]["top_lines"]` and `engine.eval.best_move`.
  2. Your 3-5 candidate moves should include at least one engine top choice and at least one strategically-motivated move that may not be in the engine's top lines.
  3. For each candidate move, populate `engine_score` and `engine_rank` if the move appears in the engine's top lines (rank 1 = engine's best move).
  4. The `rationale` must explain the **strategic logic** behind the move — not just "engine's top choice" but *why* the move works positionally: what imbalance does it exploit, what plan does it serve, what does it prevent? Bridge the gap between the engine's numerical verdict and human understanding.
  5. When a strategically-motivated move doesn't appear in the engine's top lines, the rationale should acknowledge this and explain what the strategic reasoning sees that the engine may underweight (e.g., long-term pressure, prophylaxis, practical difficulty for the opponent).
- **Phase 8** (Synthesis) — **Player's Guide fields**: Two additional fields feed the Player's Guide:
  - `position_narrative` (≥40 chars): Write in **second person** ("You have...", "Your opponent's king is exposed..."). Tell the story of the position — how the imbalances interact, where the tension lies, and what the position demands. This is the coach pointing at the board.
  - `key_takeaway` (≥20 chars): The chess lesson to internalize from this position. Not position-specific tactics, but the transferable principle (e.g., "A bishop pair advantage only matters in open positions — challenge outposted knights or open lines before they dominate").

### Step 10: Render Output

After all 9 phases are validated, generate **two documents**:

```bash
# Player's Guide — concise, coach-style narrative for learning
.venv/bin/python .claude/skills/chess-imbalances/scripts/bfih_formatter.py guide analysis/bfih_phases/ --position-data analysis/bfih_phases/position_data.json --output analysis/<filename>-guide.md

# Full BFIH Report — complete 9-phase analytical backing
.venv/bin/python .claude/skills/chess-imbalances/scripts/bfih_formatter.py render analysis/bfih_phases/ --position-data analysis/bfih_phases/position_data.json --output analysis/<filename>.md

# Console summary
.venv/bin/python .claude/skills/chess-imbalances/scripts/bfih_formatter.py summary analysis/bfih_phases/
```

The Player's Guide is the primary output — it's what a player reads to understand the position. The full BFIH report is the supporting evidence.

### Step 11: Final Validation (Optional)

Validate all phases and gates at once:

```bash
.venv/bin/python .claude/skills/chess-imbalances/scripts/bfih_validator.py validate-all analysis/bfih_phases/ --position-data analysis/bfih_phases/position_data.json
```

## Narrative Mode Workflow

When the user appends `--narrative` or asks for a game narrative/game story, follow this protocol. Requires a PGN file as input.

### Step 1: Detect Critical Moments

Run the engine sweep to find turning points:

```python
import sys
sys.path.insert(0, ".claude/skills/chess-imbalances/scripts")
from game_narrative import detect_critical_moments

moments = detect_critical_moments("path/to/game.pgn", depth=18, threshold_cp=50)
```

- `depth`: Engine search depth per position (default 18; use 12 for quick sweeps).
- `threshold_cp`: Minimum eval swing in centipawns to flag (default 50; use 80 for only major swings).
- `decay_scale_cp`: Exponential decay constant (default 750). Raises the effective threshold in lopsided positions: `effective_threshold = threshold_cp / exp(-|eval| / A)`. Gentle decay that still flags important conversion errors (e.g., premature queen trades) while filtering trivial swings in decided positions. Set to `None` to disable.
- Returns a list of `CriticalMoment` objects sorted by move number.

### Step 2: Review Critical Moments

Examine the returned moments. For each one, note:
- The eval swing direction and magnitude
- The classification (best/excellent/good/inaccuracy/mistake/blunder)
- The engine's recommended move vs what was played
- Optionally add a `key_lesson` to each moment that explains the principle violated or demonstrated

### Step 3: Classify the Arc

Based on the pattern of eval swings, classify the game arc:

| Arc Type | Pattern |
|----------|---------|
| `gradual_collapse` | Advantage builds slowly through accumulating small errors |
| `single_blunder` | Position was balanced/close until one catastrophic move |
| `back_and_forth` | Advantage swings between sides multiple times |
| `missed_opportunity` | One side had a winning position but failed to convert |
| `steady_conversion` | One side gained an early edge and methodically increased it |

### Step 4: Synthesize the Narrative

Build a `GameNarrative` model with:

```python
from game_narrative import GameNarrative, render_game_story

narrative = GameNarrative(
    game_metadata={"white": "...", "black": "...", "result": "...", "date": "...", "opening": "...", "eco": "..."},
    critical_moments=moments,  # with key_lesson populated
    arc_type="gradual_collapse",
    game_story="...",  # ≥80 chars, the connected story of the game
    key_lessons=["...", "..."],  # 1-7 transferable chess lessons
    turning_point_move=11,
    turning_point_side="white",
)
```

- `game_story`: Write a narrative connecting the critical moments into a coherent story. Second person where appropriate.
- `key_lessons`: Transferable chess principles demonstrated by this game.
- `turning_point_move` / `turning_point_side`: The single move that most decisively shifted the game's outcome.

### Step 5: Render Output

```python
md = render_game_story(narrative, output_path=Path("analysis/<filename>-narrative.md"))
```

Print a console summary after saving:

```
Saved to: analysis/<filename>-narrative.md

**Arc:** Gradual Collapse
**Turning Point:** Move 11 (White) — Be2 instead of Bg2
**Critical Moments:** N flagged across M moves
**Key Lesson:** [First lesson from the list]
```

### Combining with Deep Analysis

For a complete game study, combine narrative mode with deep analysis at critical positions:

1. Run `--narrative` to identify critical moments and the overall arc.
2. Run `--deep` at 2-4 of the most important critical positions (the turning point + key moments before/after).
3. The Player's Guides from deep analysis become the "critical moment cards" in the app, while the Game Narrative provides the connecting story and eval timeline.

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

Deep mode output is generated by `bfih_formatter.py render` from validated phase JSON. The rendered markdown includes all 9 BFIH phases with structured sections. See `references/bfih_chess_protocol.md` for the conceptual framework behind each phase.

The evidence matrix renders as a markdown table with prior→posterior in column headers:

```markdown
| Finding | H1 (0.45→0.35) | H2 (0.30→0.25) | H3 (0.15→0.30) | H_catch (0.10) |
|---------|------|------|------|---------|
| White bishop pair | ++ | + | 0 | ? |
```

## Output Behavior (Save / No-Save)

By default (`--save`, or no flag), every analysis is **saved to a file and summarized to the console**.

### Save mode (default)

1. Perform the full analysis (default or deep mode).
2. Write the complete markdown output to `analysis/<YYYY-MM-DD>_<short-description>.md` in the project root.
   - `<short-description>`: 2-4 lowercase words derived from the position (opening name, key feature, or player names). Use hyphens, no spaces. Examples: `sicilian-dragon-classical`, `carlsbad-endgame`, `queens-gambit-declined`.
   - If a file with the same name already exists, append a numeric suffix: `_2`, `_3`, etc.
3. Print a **concise console summary** (not the full analysis). The summary format:

```
Saved to: analysis/<filename>.md

**[White/Black/Equal] — [slight/clear/decisive advantage]**
Key: [1-2 sentence synthesis naming the dominant imbalances]
Plan: [Target sector] — [top 1-2 candidate moves with one-line rationale]
```

### No-save mode (`--no-save`)

Print the full analysis to the console (the standard output format templates below). Do not write any file.

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
- This skill produces strategic assessments, not engine-style evaluations. The goal is understanding, not a centipawn score. When `--engine` is used, the engine eval supplements the strategic assessment — use it to validate tactical claims and quantify advantages, not as a substitute for understanding.
- Engine integration requires Stockfish to be installed on the system. All engine functions degrade gracefully when Stockfish is unavailable.
