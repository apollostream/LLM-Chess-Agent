# Implicative Reasoning Pipeline Trace

How the General Theory of Strong Chess Playing is implemented: which deterministic functions produce evidence, and how the LLM applies structured reasoning to explain engine hypotheses.

## The Pipeline in One Diagram

```
Position (FEN)
    │
    ├──────────────────────────────────────────────────────────┐
    │ DETERMINISTIC LAYER (Python, no LLM)                    │
    │                                                          │
    │  ┌─ board_utils.analyze_position(board) ────────────┐   │
    │  │  ├── analyze_material()          → Silman #1     │   │
    │  │  ├── analyze_pawn_structure()    → Silman #2,#3  │   │
    │  │  ├── analyze_piece_activity()    → Silman #4     │   │
    │  │  ├── analyze_files()            → Silman #5     │   │
    │  │  ├── analyze_king_safety()      → Silman #6     │   │
    │  │  ├── analyze_space()            → Silman #7     │   │
    │  │  ├── analyze_development()      → Silman #8     │   │
    │  │  ├── analyze_superior_minor()   → Silman #9     │   │
    │  │  ├── analyze_initiative()       → Silman #10    │   │
    │  │  ├── analyze_statics_vs_dynamics() → composite  │   │
    │  │  └── tactical_motifs.analyze_tactics(board)      │   │
    │  │       ├── 9 static patterns (pins, batteries..)  │   │
    │  │       ├── 8 single-move threats (forks, skewers)  │   │
    │  │       └── 3 two-move sequences (deflections..)    │   │
    │  └──────────────────────────────────────────────────┘   │
    │        ↓ produces: analysis_p0 (JSON, ~15 sections)     │
    │                                                          │
    │  ┌─ engine_eval.evaluate_multipv(board) ────────────┐   │
    │  │  Stockfish UCI → score_cp, PV lines, WDL, best   │   │
    │  └──────────────────────────────────────────────────┘   │
    │        ↓ produces: engine_json (hypothesis + PV)        │
    │                                                          │
    │  ┌─ compute_pv_context(fen, analysis_p0, engine) ───┐   │
    │  │  1. analyze_pv_endpoint(fen, pv_moves)            │   │
    │  │     → plays PV, runs analyze_position at Pₙ       │   │
    │  │  2. vectorize_stm(analysis_p0) → vec_p0           │   │
    │  │     vectorize_stm(analysis_pn) → vec_pn           │   │
    │  │  3. delta = vec_pn - vec_p0 (per feature)         │   │
    │  │  4. Group by 4-tier hierarchy:                     │   │
    │  │     HUB → TACTICAL → BRIDGE → STRUCTURAL          │   │
    │  │  5. _format_tactical_motifs(p0) vs (pn)           │   │
    │  └──────────────────────────────────────────────────┘   │
    │        ↓ produces: pv_context (text block)              │
    │                                                          │
    └──────────────────────────────────────────────────────────┘
                            │
                            │ All three outputs injected into prompt
                            ▼
    ┌──────────────────────────────────────────────────────────┐
    │ REASONING LAYER (LLM, structured by _GUIDE_PROMPT)      │
    │                                                          │
    │  Step 1: POSITION ASSESSMENT                             │
    │    Read analysis_json → identify top 2-3 imbalances      │
    │                                                          │
    │  Step 2: HUB FEATURE CHANGES                             │
    │    Read pv_context tier-0 deltas → biggest Δ in          │
    │    material, initiative, dynamic/static, space            │
    │                                                          │
    │  Step 3: TACTICAL MOTIF ANALYSIS                         │
    │    Compare P₀ vs Pₙ motifs → classify each change as     │
    │    CREATION / ELIMINATION / CONVERSION / PROPHYLAXIS     │
    │                                                          │
    │  Step 4: DEPENDENCY CHAINS                               │
    │    Trace hub→tactical cascade:                            │
    │    initiative↑ → fork/skewer threats emerge               │
    │    pawn captured → file opens → rook activation           │
    │                                                          │
    │  Step 5: GAME PHASE CONTEXT                              │
    │    Weight by phase (opening/middle/endgame)               │
    │                                                          │
    │  Step 6: SYNTHESIZE                                      │
    │    Write Player's Guide grounded in evidence above        │
    └──────────────────────────────────────────────────────────┘
                            │
                            ▼
                    Player's Guide narrative
```

## What's Deterministic vs. What's LLM

| Theory Component | Implemented By | File:Function | Deterministic? |
|---|---|---|---|
| **Silman's 10 imbalances** | 12 Python functions | `board_utils.py:analyze_*` (lines 190–958) | **Yes** — pure python-chess board inspection |
| **19 tactical motifs** | 20 Python detectors | `tactical_motifs.py:detect_*` (lines 153–1109) | **Yes** — legal-move iteration + geometry |
| **Hypothesis (best move)** | Stockfish UCI | `engine_eval.py:evaluate_multipv` (line 215) | **Yes** — deterministic at fixed depth/seed |
| **Feature vectorization** | Numeric flattening | `imbalance_vectorizer.py:vectorize_stm` (line 423) | **Yes** — dict→110 numbers |
| **PV endpoint analysis** | Replay + re-analyze | `chess_pipeline.py:analyze_pv_endpoint` (line 39) | **Yes** — same board_utils at endpoint |
| **Feature deltas P₀→Pₙ** | Vector subtraction | `chess_pipeline.py:compute_pv_context` (line 287) | **Yes** — arithmetic |
| **4-tier hierarchy** | Feature classification | `chess_pipeline.py:_tier_label` (line 111) | **Yes** — set membership lookup |
| **Motif formatting** | Type-specific formatters | `chess_pipeline.py:_format_tactical_motifs` (line 124) | **Yes** — string templates |
| **Position assessment** | LLM reads evidence | `agent_service.py:_GUIDE_PROMPT` step 1 | **No** — LLM judgment |
| **Hub→tactical cascades** | LLM traces chains | `agent_service.py:_GUIDE_PROMPT` step 4 | **No** — LLM reasoning |
| **Narrative synthesis** | LLM writes prose | `agent_service.py:_GUIDE_PROMPT` step 6 | **No** — LLM composition |

## The Critical Insight

The boundary is sharp and deliberate:

1. **Everything the LLM receives as input is deterministically computed.** The imbalances, tactical motifs, engine PV, feature deltas, and motif comparisons (P₀ vs Pₙ) are all produced by Python algorithms operating on `chess.Board`. The LLM cannot invent evidence — it can only read what the pipeline computed.

2. **The 6-step Playbook algorithm constrains how the LLM reasons.** Steps 1-5 each reference specific computed evidence: "From the PV deltas above" (step 2), "Compare tactical motifs at P₀ vs the PV endpoint" (step 3). The LLM is told to classify motif changes as CREATION/ELIMINATION/CONVERSION/PROPHYLAXIS — an ontology it applies to deterministically-computed motif diffs.

3. **The LLM's contribution is exactly the _implicative reasoning_ itself** — connecting evidence to hypothesis. The deterministic layer answers "what changed?" (deltas) and "what exists?" (motifs). The LLM answers "why does this explain the engine's recommendation?" That's the part that requires understanding chess concepts like "a pin on the f-file restricts the king's escape" — but it's constrained to reason _from_ the pipeline's evidence, not from training data memory.

4. **The vectorizer + delta computation implement the "state transition" part of the General Theory.** `vectorize_stm()` at P₀ and Pₙ produces two state vectors; subtraction gives the transition. The 4-tier hierarchy (empirically derived from the precision matrix analysis) tells the LLM which changes have the broadest explanatory reach — hubs first, then tactical, then bridge, then structural.

## The 4-Tier Hierarchy: Empirical Foundations

The tier ordering — HUB → TACTICAL → BRIDGE → STRUCTURAL — is not a theoretical axiom or chess dogma. It was **discovered empirically** from a precision matrix computed via Graphical Lasso on a corpus of real chess games.

### The Dataset

**28,454 position transitions** extracted from **250 games**:
- 100 TCEC super-engine games
- 99 super-GM games (2500+ ELO)
- 51 intermediate games (~1200–1500 ELO)

Each transition is a pair (P_before, P_after) — one half-move apart. Both positions are run through `board_utils.analyze_position()` → `imbalance_vectorizer.vectorize_stm()`, producing 74-dimensional STM-relative feature vectors. The **deltas** (feature changes per move) form the dataset.

### The Algorithm

**Graphical Lasso** (`sklearn.covariance.GraphicalLassoCV`, 5-fold CV) with optimal regularization α = 0.2162. This estimates the **precision matrix** Ω — the inverse covariance matrix — where zero entries encode **conditional independence**: features i and j are conditionally independent given all other features when Ω[i,j] = 0.

**Result**: 94.1% sparse (only 147–159 non-zero edges out of ~2,556 possible). This validates treating imbalances as largely independent assessments — most feature pairs don't interact once you condition on everything else.

**Partial correlations** (the actual relationship strengths) are computed as:
```
ρ(i,j | rest) = −Ω[i,j] / √(Ω[i,i] · Ω[j,j])
```
Note the negation — raw precision entries have the **opposite sign** from the intuitive relationship direction.

### How the Tiers Were Identified

**Node degree** in the precision matrix graph (count of non-zero |Ω[i,j]| > 0.001 per feature) determines explanatory reach:

```
Tier 0 — HUB FEATURES (degree 7–14, broadest reach)
  ┌─────────────────────────────┬────────┬──────────────────────────────────────┐
  │ Feature                     │ Degree │ Why it's a hub                       │
  ├─────────────────────────────┼────────┼──────────────────────────────────────┤
  │ material_advantage          │   14   │ Most-connected; touches every domain │
  │ initiative_score_stm/opp    │  9-10  │ Co-moves with tactical motifs        │
  │ pawn_count_stm/opp          │   8-9  │ Pawn captures cascade to files,      │
  │                             │        │ material, structure                   │
  │ static_score_stm/opp        │   7-8  │ Aggregates pawn & positional quality │
  │ dynamic_score_stm/opp       │    7   │ Aggregates threats & initiative      │
  │ space_stm/opp               │   6-7  │ Broad board control metric           │
  └─────────────────────────────┴────────┴──────────────────────────────────────┘

Tier 1 — TACTICAL MOTIFS (degree 2–5, connected primarily via initiative hub)
  fork_threats (ρ = +0.37 with initiative)
  checks_available (ρ = +0.32 with initiative)
  skewer_threats (ρ = +0.15 with initiative)
  discovered_attacks (ρ = +0.13 with initiative)
  Key finding: these CO-MOVE with initiative — they emerge together,
  not as substitutable channels

Tier 2 — BRIDGE FEATURES (degree 5–7, connect hubs to specifics)
  semi_open_files (ρ = −0.20 with pawn_count — pawn captured → file opens)
  passed_pawns, queen/rook counts — medium connectivity, link material
  to positional consequences

Tier 3 — STRUCTURAL (degree 2–5, localized effects)
  isolated/doubled/backward pawns, development, castling, king safety
  These affect static_score but don't propagate widely

Degree 0 — ORTHOGONAL (conditionally independent of everything)
  trapped_pieces, open_files — check independently, no cascading effects
```

### What the Precision Matrix Tells the Reasoning Algorithm

The empirical structure dictates Step 2 of the Playbook prompt — **"HUB FEATURE CHANGES: From the PV deltas above, identify the most significant changes"**:

1. **Assess hub features first** because they have the broadest explanatory reach (degree 7–14). A change in initiative explains co-occurring changes in fork/skewer/check threats. A change in pawn count explains file openings. Starting here gives the LLM the widest context.

2. **Follow dependency chains** because the precision matrix reveals **which features co-move** and in what direction:
   - `initiative ↑` → `fork_threats ↑, checks ↑, skewers ↑` (positive partial correlations: ρ = +0.13 to +0.37)
   - `pawn_count ↓` → `semi_open_files ↑` (negative partial correlation: ρ = −0.20)
   - `isolated_pawns ↑` → `static_score ↓` (ρ = −0.21)

   These aren't chess maxims — they're measured conditional dependencies from 28K positions. The Playbook's Step 4 ("DEPENDENCY CHAINS") operationalizes them.

3. **Check orthogonal signals independently** — degree-0 features (trapped pieces, open files) are conditionally independent of everything else. They provide information that no other feature predicts, so they must be assessed separately, not derived from hub changes.

### The Epistemological Point

This is what makes the Theory empirically grounded rather than just "chess intuition formalized":

- **The feature set** (Silman's 10 imbalances + 19 tactical motifs) is the **ontology** — a human-designed categorization of chess-relevant concepts. This is a design choice, not an empirical discovery.

- **The tier hierarchy** is an **empirical discovery** — the precision matrix reveals which features have the broadest conditional dependencies in real games. Material advantage being the most-connected hub (degree 14) with weak individual partial correlations (|ρ| < 0.13) means it touches everything but determines nothing alone. Initiative co-moving with tactical motifs (ρ = +0.37 for forks) is a measured fact, not a teaching heuristic.

- **The reasoning algorithm** (6-step Playbook) **operationalizes the empirical structure** — it tells the LLM to traverse the dependency graph in the order that maximizes explanatory coverage: hubs first, then their tactical descendants, then bridges, then structural details.

The precision matrix is symmetric (no causal direction without temporal ordering), and the Gaussian assumption misses nonlinear chess interactions (R² = 0.779 leaves 22% unexplained). These are honest limitations documented in the analysis. The framework is explanatory (why a move is good), not predictive (which move is best) — Stockfish provides the prediction, the Theory provides the explanation.

## Where the Formatter Fix Mattered

Before the fix, `_format_tactical_motifs()` used generic keys that didn't match the actual schema. This meant the LLM received empty or garbled tactical evidence — so any tactical reasoning in the narrative was necessarily from training data, not from pipeline evidence. After the fix, pins show `pinner/pinned_piece/pinned_to`, skewers show `move/skewering_piece/front_target/rear_target`, etc. The Erdogmus playbook proved the pipeline works: the narrative identified Qxf2+!! from the convergence of pin + x-ray + removal-of-guard + latent skewers — all explicitly present in the formatted evidence.

## Terminology

In the context of the implicative reasoning framework:

- **"Imbalances"** — the 10 Silman positional features (material, pawn structure, piece activity, files, king safety, space, development, superior minor piece, initiative, statics vs dynamics)
- **"Tactical motifs"** — the 19 detected patterns across 3 tiers (static board patterns, single-move threats, 2-move forced sequences); close synonyms: "threats" and "opportunities" depending on context
- **"Evidence"** — collectively, imbalances and tactical motifs when used in the reasoning process to support hypotheses about good moves
- **"Hypothesis"** — the engine's recommended best move (from Stockfish multi-PV)
- **"Data"** — reserved strictly for corpus/database contexts (e.g., "precision matrix computed from game data", "frequency of this motif in the data"); never used for imbalances or tactical motifs in analysis output
