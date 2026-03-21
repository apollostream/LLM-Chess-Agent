# Hypothesis Ontology & Implicative Chain Assessment

## The Problem

LLMs suffer from "errors of construction" — getting component pieces correct but assembling them incorrectly. Our methodology imposes an implicative reasoning chain: FEN → imbalances → tactics → move (PV eval). But the chain is only partially imposed. The evidence production is deterministic; the reasoning construction is unconstrained LLM prose.

To close this gap, we need **computed implication chains** — predictive rules derived from our database of 28K position transitions that formally connect evidence to explanatory hypotheses to move justifications.

## The Unsolved Core Problem: What Are "Hypotheses"?

The features (imbalances, tactical motifs) are **evidence**. The engine's best move is the **conclusion**. But what are the **intermediate explanatory hypotheses** that chain evidence to conclusion?

### Four Levels of Explanation

```
Level 0 (Observable):   "A pin exists on the f-file"
                        "Black has an isolated pawn on d5"
                        → These are EVIDENCE (we compute them deterministically)

Level 1 (Mechanism):    "The pin restricts king escape"
                        "The isolated pawn creates a target on d5"
                        → These are IMPLICATIONS (not yet computed)

Level 2 (Strategic):    "Kingside attack is viable"
                        "Minority attack exploits queenside weaknesses"
                        → These are PLANS (not yet computed)

Level 3 (Outcome):      "White wins material"
                        "Black's position collapses"
                        → These are PREDICTIONS (GBR approximates, R²=0.871)
```

Our system currently jumps from Level 0 to Level 3 (via GBR regression) or hands the entire chain to unconstrained LLM prose. The computed implication chains need to fill **Levels 1 and 2** — mechanism and strategic plan — with formally derived, empirically validated rules.

## What Already Exists (≈40% Complete)

### Data Infrastructure (Done)
- 28,454 position transitions across 250 games (100 TCEC, 99 super-GM, 51 intermediate)
- 74-dimensional STM-relative feature vectors per transition (`imbalance_vectorizer.py`)
- Engine eval cache for all positions (`game_store.py`)
- PV replay with structural features at each ply (`pv_state_chain.py`)
- Feature delta computation (`compute_deltas()`)

### Statistical Structure (Done)
- Precision matrix (Graphical Lasso, α=0.2162, 94.1% sparse, 159 edges)
- 4-tier hierarchy (HUB → TACTICAL → BRIDGE → STRUCTURAL) from node degree
- Partial correlations with corrected signs

### Predictive Models (Done, Needs Validation)
- GBR predicting Δeval from feature deltas: R² = 0.871 (but no cross-validation — true generalization unknown)
- PV comparison model predicting eval gaps from structural diffs: R² = 0.913
- Feature importance rankings (permutation-based): d_checks_available, d_initiative_score, d_space, d_fork_threats

### Move Archetypes (Embryonic)
- 6 K-Means clusters on delta vectors
- Statistical groupings, NOT chess-meaningful strategic categories
- Example: Cluster 3 = "strong move" (Δeval +59cp, initiative↑, fork_threats↑)

## What's Missing

### 1. Directed Graph (Precision Matrix → DAG)
**Have:** Undirected conditional independence structure (159 edges).
**Need:** Edge orientation via PC algorithm + temporal ordering from PV replays (which feature changes first in the engine's recommended line). Result: a DAG where edges mean "change in X implies change in Y."
**Status:** Not started.

### 2. Level 1 — Mechanism Rules (Implicit → Explicit)
**Have:** GBR has implicitly learned mechanism rules (R²=0.871).
**Need:** Explicit rule extraction — decision tree `export_text()`, association rule mining with confidence/coverage/lift metrics.
**Example target rules:**
```
IF pin_count > 0 AND king_adjacent_to_pin_line
   THEN king_escape_squares_reduced
   (confidence: 0.89, coverage: 412 positions)

IF pawn_captured AND file_was_closed
   THEN semi_open_file_created
   (confidence: 0.97, coverage: 1,847 positions)
```
**Status:** Model exists; rule extraction not performed.

### 3. Level 2 — Strategic Plan Taxonomy
**Have:** 6 statistical archetypes from K-Means.
**Need:** Chess-meaningful plan categories — "kingside attack", "central breakthrough", "queenside minority attack", "endgame conversion", "piece coordination improvement" — and classifiers predicting which plan a move serves.
**Approaches:**
- Manual labeling of position subset + supervised learning
- Unsupervised discovery with human-interpretable cluster descriptions
- LLM-assisted labeling validated against delta patterns
**Status:** Clustering exists; mapping to strategic concepts not done. This is the hardest problem.

### 4. Chain Construction & Validation
**Have:** Nothing.
**Need:** Multi-step chains (e.g., `pin_exists → king_escape_restricted → sacrifice_enabled → material_gain`) validated against PV ground truth: in positions where the full chain's antecedent is true, does the consequent hold?
**Status:** Requires steps 1-3 first.

### 5. Cross-Validation & Generalization Testing
**Have:** R²=0.871 on training data.
**Need:** Stratified train/test splits (by game, phase, archetype), out-of-distribution test sets, confidence intervals.
**Status:** Not done. True generalization unknown.

### 6. Game-Phase Stratification
**Have:** All data pooled.
**Need:** Separate rules/models per phase — opening (development, center), middlegame (initiative, tactics, king safety), endgame (passed pawns, king activity).
**Status:** Not done.

## Summary Table

| Component | Status | What Exists | What's Missing |
|---|---|---|---|
| Evidence (Level 0) | **Done** | board_utils, tactical_motifs, vectorizer | — |
| Mechanism rules (Level 1) | **Implicit** | GBR has learned them (R²=0.87) | Explicit rule extraction, confidence/coverage |
| Strategic plans (Level 2) | **Embryonic** | 6 K-Means archetypes | Chess-meaningful plan taxonomy, classifiers |
| Outcome prediction (Level 3) | **Done** | GBR Δeval prediction | Cross-validation needed |
| Directed structure | **Half done** | Precision matrix skeleton | PC algorithm, temporal edge orientation |
| Chain construction | **Not started** | — | Requires Levels 1-2 + directed graph |
| Chain validation | **Not started** | — | Requires chains + PV ground truth |

## Roadmap

**Phase 1 — Extract what's already learned (immediate):**
1. Cross-validate GBR and PV models → measure true generalization
2. Extract decision tree rules from GBR → explicit Level 1 mechanism rules
3. Compute rule coverage/confidence/lift
4. Stratify by game phase, retrain phase-specific models

**Phase 2 — Directed structure (days):**
1. PC algorithm on precision matrix skeleton (pgmpy)
2. Temporal edge orientation from PV replay data
3. Build Bayesian network with learned CPTs
4. Validate DAG against chess domain knowledge

**Phase 3 — Strategic plan taxonomy (weeks):**
1. Define chess-meaningful plan categories (human ontology design)
2. Label subset of positions with plan tags
3. Train multi-class classifier predicting plan from position features
4. Map K-Means archetypes to plan categories

**Phase 4 — Chain construction & integration (weeks):**
1. Chain Level 1 rules into multi-step implication paths
2. Validate chains against PV ground truth
3. Integrate into pipeline as computed implication chains (Approach 3)
4. Constrain LLM to translate computed chains to prose, not construct them
