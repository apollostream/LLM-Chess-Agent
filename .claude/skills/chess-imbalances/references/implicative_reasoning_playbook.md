# Implicative Reasoning Playbook: A General Theory of Chess Move Explanation

*Version 1.0 — 2026-03-17*

## Purpose

Given a chess position P₀ and an engine's principal variation (PV) with eval score, produce a **deterministic, reproducible explanation** of *why* the engine's suggested move is best. The explanation is grounded in empirically measured feature changes, not improvised narrative.

This playbook is **explanatory** (why is this move best?) not **predictive** (which move is best?). The engine provides the verdict; this framework provides the structured reasoning.

---

## Theoretical Foundation

The playbook rests on three empirical results from 28,454 position transitions across 250 games (100 TCEC super-engine, 99 super-GM 2500+, 51 intermediate):

1. **Eval prediction from feature deltas** (Section 12): A Gradient Boosting Regressor predicts 77.9% of eval change variance (R² = 0.779) from 76 feature deltas. The top predictors are: material_advantage (61.2%), initiative_score (8.4%), pawn_count (4.1%), dynamic_score (3.2%), space (2.8%).

2. **Conditional independence structure** (Section 18): 94.1% of feature pairs are conditionally independent. The 159 non-zero edges organize into a tiered hierarchy: hub features (broad but weak connections), bridge features (connecting domains), and independent signals (orthogonal, must check separately).

3. **Tactical co-movement** (Sections 17-18): Initiative and tactical motifs have positive partial correlations — they emerge together, not as substitutes. Fork threats (ρ = +0.37), checks available (ρ = +0.32), skewer threats (ρ = +0.15), discovered attacks (ρ = +0.13) all co-move with initiative.

---

## The Algorithm

### Input

- **Position P₀**: The current board state (FEN)
- **Engine PV**: The engine's best line [M₁, m₂, m₃, ..., mₙ]
- **Eval score**: The engine's evaluation of P₀ after M₁
- **Analysis JSON at P₀**: Full `analyze_position()` output (imbalances + tactics)
- **Analysis JSON at P_n**: Full `analyze_position()` output at the PV endpoint
- **Side to move (STM)**: Who plays M₁

### Step 1: Compute Feature States and Deltas

Extract the 76-feature vector at P₀ and P_n. All features are expressed from STM's perspective (STM/OPP, not White/Black). Compute:

```
Δ = features(P_n) − features(P₀)
```

Partition the features into three categories for separate analysis:

**A. Positional Imbalances (Silman's framework):**
- material_advantage, bishop_pair, queen/rook/minor/pawn counts
- passed_pawns, doubled/isolated/backward_pawns, pawn_islands
- space, center_control, squares_attacked
- development, castling_rights
- king_attackers, pawn_shield, missing_shield
- knight_outposts, bad_bishops, rooks_on_open_files, rooks_on_7th
- initiative_score, static_score, dynamic_score

**B. Tactical Motifs (16 features):**

| Feature | Type | Description |
|:---|:---|:---|
| fork_threats_stm/opp | Count | Number of fork threats per side |
| skewer_threats_stm/opp | Count | Number of skewer threats per side |
| discovered_attack_threats_stm/opp | Count | Discovered attack opportunities per side |
| checkmate_threats_stm/opp | Count | Mate threat patterns per side |
| checks_available_stm/opp | Count | Legal checking moves per side |
| mate_threat_by_stm/opp | Binary | Does this side threaten checkmate? |
| pin_count | Count | Total pins on the board |
| battery_count | Count | Total batteries (aligned heavy pieces) |
| hanging_pieces_count | Count | Undefended pieces |
| trapped_pieces_count | Count | Pieces with no safe squares |

**C. Context:**
- game_phase (0 = opening, increasing toward endgame)
- total_non_pawn_material
- is_check

### Step 2: Rank Significant Deltas

A delta is **significant** if it represents a meaningful change in the position. Rank by importance using the empirical feature importance weights:

**Tier 1 — Hub features (assess first, broadest explanatory reach):**
- Δmaterial_advantage (importance: 0.612, degree 14)
- Δinitiative_score_stm (importance: 0.084, degree 10)
- Δpawn_count_stm/opp (importance: 0.041, degree 8-9)
- Δdynamic_score_stm (importance: 0.032, degree 7)
- Δspace_stm (importance: 0.028, degree 6)
- Δstatic_score_stm (importance: 0.018, degree 7)

**Tier 2 — Bridge features (connect hubs to specifics):**
- Δpassed_pawns, Δsemi_open_files, Δqueen_count, Δrook_count
- Δfork_threats_stm/opp, Δchecks_available_stm/opp

**Tier 3 — Structural features (assess as groups):**
- Δisolated/doubled/backward_pawns (pawn structure block)
- Δdevelopment, Δcastling_rights (development block)
- Δking_attackers, Δpawn_shield, Δmissing_shield (king safety block)

**Tier 4 — Leaf features:**
- Δbad_bishops, Δknight_outposts, Δrooks_on_files, Δcenter_control

**Tier 5 — Independent signals (orthogonal, check separately):**
- Δtrapped_pieces, Δopen_files

Report only features with Δ ≠ 0. Among non-zero deltas, emphasize those in higher tiers first.

### Step 3: Trace Dependency Chains

For each significant hub/bridge delta, use partial correlations to trace downstream consequences. The chains below are empirically validated (|ρ| > 0.10):

**Initiative chain (positive co-movement):**
```
Δinitiative_score_stm ↑
  → Δfork_threats_stm ↑        (ρ = +0.37)
  → Δchecks_available_stm ↑    (ρ = +0.32)
  → Δskewer_threats_stm ↑      (ρ = +0.15)
  → Δdiscovered_attacks_stm ↑  (ρ = +0.13)
  → Δdynamic_score_stm ↑       (ρ = +0.10)
```
When initiative increases, *multiple* tactical possibilities emerge simultaneously. Report which specific motifs appeared.

**Pawn structure chain (file opening):**
```
Δpawn_count_stm ↓ (pawn captured or exchanged)
  → Δsemi_open_files_stm ↑     (ρ = −0.20, inverse: fewer pawns → more open files)
  → Δstatic_score_stm changes  (ρ = −0.13)
```
When pawns are exchanged, files open. Check if rooks can exploit new semi-open files.

**Material chain (board control):**
```
Δmaterial_advantage ↑
  → Δsquares_attacked_stm ↑    (ρ = +0.12)
  → Δsquares_attacked_opp ↓    (ρ = −0.13)
```
Material gains shift board control — more pieces mean more squares covered.

**Development chain (dynamism):**
```
Δdevelopment_stm ↑
  → Δdynamic_score_stm ↑       (ρ = +0.11)
  → Δdynamic_score_opp ↓       (ρ = −0.13)
```
Development improves your dynamism while constraining the opponent's.

**King safety chain:**
```
Δpawn_shield_stm ↔ Δmissing_shield_stm  (ρ = −0.39, inverse measures)
Δking_attackers changes → check king exposure
```

### Step 4: Tactical Motif Analysis (First-Class)

Tactical motifs are NOT just another row in the delta table. They are the **concrete mechanisms** through which positional advantages are expressed. This step examines them in detail.

**4a. Identify tactical motif deltas:**

For each tactical feature, compare P₀ vs P_n:

| Motif | P₀ (STM) | P_n (STM) | Δ | P₀ (OPP) | P_n (OPP) | Δ |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| Fork threats | | | | | | |
| Skewer threats | | | | | | |
| Discovered attacks | | | | | | |
| Checkmate threats | | | | | | |
| Checks available | | | | | | |
| Mate threat | | | | | | |
| Pins | | | | | | |
| Batteries | | | | | | |
| Hanging pieces | | | | | | |
| Trapped pieces | | | | | | |

**4b. For each significant tactical delta, describe the concrete motif:**

Use the raw tactical analysis JSON (not just counts) to identify:
- **Which piece** creates or suffers the motif (e.g., "knight on e5 forks queen on d7 and rook on g4")
- **Which squares** are involved
- **Which side** benefits
- **Whether it's new** (appeared during the PV) or **resolved** (present at P₀, gone at P_n)

**4c. Classify the tactical role in the PV:**

- **Tactical threat creation**: The PV creates new threats (Δfork_threats_stm > 0). The engine's move is best because it generates concrete threats the opponent must address.
- **Tactical threat elimination**: The PV resolves opponent threats (Δfork_threats_opp < 0, Δmate_threat_by_opp: 1→0). The engine's move is best because it neutralizes danger.
- **Tactical conversion**: Positional advantage converts to tactical advantage (Δinitiative↑ and Δtactical_motifs↑ simultaneously). The engine's move is best because it *cashes in* a positional edge.
- **Prophylactic defense**: The PV prevents future tactical motifs from appearing (opponent's Δchecks_available↓, Δdiscovered_attacks↓). The engine's move is best because it restricts the opponent's tactical potential.

### Step 5: Game Phase Weighting

The importance of different features shifts across game phases. Apply phase-appropriate emphasis:

**Opening (game_phase < 0.3, material ≈ full):**
- Prioritize: development, center_control, castling_rights, initiative
- De-prioritize: passed_pawns, rooks_on_7th, endgame pawn structure
- Tactical emphasis: development-based tactics (pins on undeveloped pieces, fork threats from active minor pieces)

**Middlegame (0.3 ≤ game_phase < 0.7):**
- Prioritize: initiative_score, space, king_safety (attackers, shield), tactical motifs
- Key dynamic: initiative→tactical co-movement is strongest here
- Tactical emphasis: all motifs relevant; fork/skewer/discovered attack creation; king attack combinations

**Endgame (game_phase ≥ 0.7, reduced material):**
- Prioritize: passed_pawns, king activity (king_attackers reinterpreted), pawn_structure
- De-prioritize: castling_rights (usually gone), development (complete)
- Tactical emphasis: promotion threats, zugzwang indicators, trapped pieces, simplification tactics

### Step 6: Synthesize the "Why"

Combine Steps 2-5 into a structured explanation. The synthesis follows this template:

> **Position Assessment (from P₀ features):**
> [Side] stands [better/worse/equal] due to [top 2-3 imbalances favoring each side]. The position is [static/dynamic] in character ([game phase]).
>
> **Why the engine recommends [move]:**
> This move initiates a sequence that achieves [primary hub-level change: e.g., "wins a pawn," "seizes the initiative," "opens the d-file"]. The mechanism is [dependency chain: e.g., "the pawn capture on d5 opens the d-file (Δsemi_open_files_stm +1), activating the rook on d1"].
>
> **Tactical justification:**
> The PV [creates/eliminates/converts] the following tactical motifs: [specific motifs with piece descriptions from raw analysis]. [E.g., "After 15.Nxd5, White creates a fork threat — the knight on d5 simultaneously attacks the queen on b6 and the rook on f4. Black's best response 15...Qc7 avoids the fork but concedes the center."]
>
> **Secondary effects:**
> [Any additional significant deltas: space changes, king safety shifts, structural improvements]
>
> **What the features don't capture (if applicable):**
> [If the eval swing is large but feature deltas are modest, acknowledge deep tactical content: "The +3.2 eval swing exceeds what the positional changes alone explain — the PV contains a forcing sequence that wins material through a combination invisible to static feature analysis."]

### Step 7: Residual Acknowledgment

The feature-based model explains ~78% of eval variance (R² = 0.779). When the eval delta from the PV significantly exceeds what the feature deltas would predict:

- **Small residual** (eval swing ≈ feature-predicted swing): The explanation is likely complete. State confidently.
- **Moderate residual** (eval swing 1.5-3× feature prediction): Some tactical depth not captured by features. Note the discrepancy: "The engine sees deeper than the positional features suggest — likely a forcing tactical sequence."
- **Large residual** (eval swing >3× feature prediction): The move's value is primarily tactical/calculational, not positional. Describe the feature changes that do exist, but acknowledge: "This move's strength lies in concrete calculation that transcends positional features."

---

## Feature Reference Card

### Positional Imbalances → JSON Fields

| Imbalance | Features | Partial Corr with Eval |
|:---|:---|:---|
| Material | material_advantage, queen/rook/minor/pawn_count | Strongest predictor (0.612) |
| Pawn Structure | passed/doubled/isolated/backward_pawns, pawn_islands | Moderate (via static_score) |
| Space | space_stm/opp, center_control, squares_attacked | ρ = +0.30 with squares_attacked |
| Development | development_stm/opp | Opening/early middlegame |
| Initiative | initiative_score_stm/opp | Second strongest (0.084) |
| King Safety | pawn_shield, missing_shield, king_attackers, castling_rights | Block structure (ρ = −0.39 shield↔missing) |
| Minor Pieces | bishop_pair, bad_bishops, knight_outposts, minor_piece_score | Leaf features |
| Files | open_files, semi_open_files, rooks_on_open_files, rooks_on_7th | Pawn-driven chain |

### Tactical Motifs → JSON Fields

| Motif | Feature(s) | Raw Analysis JSON Path | Relationship to Initiative |
|:---|:---|:---|:---|
| Forks | fork_threats_stm/opp | tactics.threats.forks[] | ρ = +0.37 (co-moves) |
| Skewers | skewer_threats_stm/opp | tactics.threats.skewers[] | ρ = +0.15 (co-moves) |
| Discovered Attacks | discovered_attack_threats_stm/opp | tactics.threats.discovered_attacks[] | ρ = +0.13 (co-moves) |
| Checks | checks_available_stm/opp | initiative.checks_available | ρ = +0.32 (co-moves) |
| Checkmate Threats | checkmate_threats_stm/opp, mate_threat_by_stm/opp | tactics.threats.checkmate_threats[], king_safety.mate_threat | ρ = +0.57 (redundant measures) |
| Pins | pin_count | tactics.static.pins[] | Degree 0 (independent) |
| Batteries | battery_count | tactics.static.batteries[] | Degree 0 (independent)* |
| Hanging Pieces | hanging_pieces_count | tactics.static.hanging_pieces[] | Weak (ρ = +0.04) |
| Trapped Pieces | trapped_pieces_count | tactics.static.trapped_pieces[] | Degree 0 (independent) |

*Independent signals must be checked separately — they cannot be predicted from positional features.*

### Dependency Chain Quick Reference

```
material_advantage ──(ρ=+0.12)──→ squares_attacked_stm
                   ──(ρ=−0.13)──→ squares_attacked_opp

initiative_score   ──(ρ=+0.37)──→ fork_threats
                   ──(ρ=+0.32)──→ checks_available
                   ──(ρ=+0.15)──→ skewer_threats
                   ──(ρ=+0.13)──→ discovered_attacks
                   ──(ρ=+0.10)──→ dynamic_score

pawn_count         ──(ρ=−0.20)──→ semi_open_files (inverse: fewer pawns → more files)

development        ──(ρ=+0.11)──→ dynamic_score_stm
                   ──(ρ=−0.13)──→ dynamic_score_opp

isolated_pawns     ──(ρ=−0.21)──→ static_score (weaknesses reduce score)
doubled_pawns      ──(ρ=−0.16)──→ static_score
backward_pawns     ──(ρ=−0.13)──→ static_score

pawn_shield        ──(ρ=−0.39)──→ missing_shield (inverse measures)
```

---

## Honest Limitations

1. **22% unexplained variance.** The feature model cannot capture deep tactical sequences (7-move combinations, quiet intermediate moves, zugzwang). The residual protocol (Step 7) addresses this explicitly.

2. **Gaussian assumption.** The partial correlations assume linear conditional relationships. Chess features interact nonlinearly — a knight outpost might be worthless in an endgame but decisive in a middlegame. Game phase weighting (Step 5) partially compensates.

3. **No causal direction.** The precision matrix is symmetric. We say "initiative co-moves with fork threats" but cannot distinguish "initiative creates forks" from "forks create initiative" without temporal ordering within the PV. The dependency chains above use domain knowledge to impose causal direction.

4. **Contemporaneous deltas.** Features are computed at P₀ and P_n (endpoints). Intermediate positions in the PV may have different tactical landscapes. A sacrifice at move 2 of the PV might temporarily reduce material before winning it back at move 6. The endpoint comparison captures the net effect, not the journey.

5. **Feature granularity.** "fork_threats_stm = 2" tells you there are two fork threats but not whether they're devastating or trivially parried. The raw tactical analysis JSON provides the details; the playbook relies on Claude to read and interpret them.
