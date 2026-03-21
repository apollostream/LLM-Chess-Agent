# App Vision: How It All Comes Together

How the implicative reasoning methodology ensures meaningful chess narratives, and what makes this app novel for chess players.

## Five Layers of Narrative Constraint

Each layer progressively tightens what the LLM can say, reducing the space for construction errors:

```
Layer 1: EVIDENCE PRODUCTION (deterministic)
  board_utils.py → 10 imbalances + 19 tactical motifs
  "These features exist in this position" — LLM can't invent them

Layer 2: PV TRANSFORMATION (deterministic)
  compute_pv_context() → feature deltas P₀ → Pₙ
  "These features CHANGED along the engine's recommended line"

Layer 3: RELEVANCE HIERARCHY (empirical)
  Precision matrix → 4-tier ordering (hub → tactical → bridge → structural)
  "Assess these features FIRST — they have the broadest explanatory reach"

Layer 4: FEATURE SELECTION (computed)
  MRE → GBF-ranked most relevant feature subset
  "THESE specific features are the most relevant explanation for the eval change"

Layer 5: REASONING ALGORITHM (prompt-constrained)
  6-step Playbook → assessment → hubs → tactics → chains → phase → synthesis
  "Follow THIS algorithm to connect the evidence to the conclusion"
```

**What's proven**: Layers 1-4 are deterministic/computed. MRE explanations make chess sense (symmetric improvement/decline, explaining-away works, neutral = "nothing changed").

**What's NOT proven**: Layer 5 — the LLM still constructs the narrative freely within MRE-selected features. Ablation study (does MRE-constrained LLM outperform unconstrained?) and corruption test (does the LLM follow wrong MRE or override from training data?) are needed before publication claims.

## The Transformations Enhancement (Next Major Step)

Currently, PV deltas tell us WHAT changed (P₀ → Pₙ endpoint comparison). MRE tells us WHICH changes matter most. But neither tells us HOW the changes connect — the causal/implicative chain between feature transitions.

**Per-ply PV replay** would compute the chain explicitly:

```
P₀ → P₁ (Nxd5):  material +3, pawn_count_opp -1
P₁ → P₂ (Rd1):   semi_open_files +1, initiative +2
P₂ → P₃ (Rd7):   rooks_on_7th +1, initiative +1
```

Now the chain is computed: **capture → file opens → rook activates → 7th rank penetration**. The LLM doesn't construct this chain — it translates it to prose.

**Infrastructure already exists**: `pv_state_chain.py:replay_pv()` replays PV moves and collects features at each ply. It's used for the feature extraction dataset but not yet wired into the narrative pipeline. This is the next major enhancement — connecting per-ply feature transitions to the Player's Guide and Game Synopsis.

## Game Synopsis: MRE-Grounded Critical Moments

The Game Synopsis pipeline with MRE integration:

```
PGN → Stockfish sweep → detect critical moments (eval swings > 50cp)
  ↓
For each critical moment:
  → MRE: computed most relevant features for this eval swing
  → Transformation chain: per-ply feature transitions along the PV
  → Player's Guide: narrative constrained by MRE + transformation chain
  ↓
Synthesis: connect critical moments via their MRE signatures
  → Arc type (gradual collapse, single blunder, back-and-forth, etc.)
  → MRE signature per moment: "material-initiative swing" vs "structural transformation"
  → Key lessons, turning point
```

Each critical moment gets a computed *signature* from MRE — the synopsis connects signatures into a narrative arc:

> "The game turned on three material-initiative swings: at move 15, White's knight sacrifice opened the position (MRE: material, initiative, files). Black fought back at move 22 with a counter-sacrifice (MRE: material exchange, king safety). But White's final combination at move 31 (MRE: initiative, fork threats, opp_kingside control) was decisive."

## Competitive Landscape (Honest Assessment)

| System | What It Does | What It Lacks |
|---|---|---|
| **Chess.com / Lichess** | Engine eval + best move | No WHY — just numbers |
| **DecodeChess** | Rule-based NL explanations | Template-driven, no empirical feature selection |
| **ChessBase** | Engine + commentary templates | No imbalance-grounded reasoning |
| **AlphaZero XAI papers** | SHAP/concept probing on neural nets | Explains the MODEL, not the POSITION for humans |
| **Our approach** | Empirical BN → MRE → constrained LLM narrative | Unproven at scale (ablation needed) |

## What's Genuinely Novel

1. **Empirical feature hierarchy** — not chess dogma, but measured conditional dependencies from 28K positions via Graphical Lasso. The 4-tier ordering (hub → tactical → bridge → structural) is discovered, not assumed.

2. **Computed relevance (MRE)** — not "the LLM thinks material matters" but "GBF = 2.35 says material is the statistically most relevant explanation for this eval change." Based on Yuan et al.'s Generalized Bayes Factor with proper formula: GBF(x,e) = P(e|x) / P(e|¬x).

3. **Explaining away** — if material already explains the eval improvement, the system doesn't redundantly mention space. The GBF automatically prunes irrelevant variables. No other chess tool does this.

4. **Sharp deterministic/LLM boundary** — the LLM composes prose, but the evidence selection is computed. Architecturally unique: five layers of constraint before the LLM speaks.

5. **Spatial context in the BN** — 9 STM-relative spatial features (regional control + king location) empirically confirmed as load-bearing (all degree ≥ 4 in the precision matrix). Enables MRE explanations like "fork threats + opponent kingside control" → spatially grounded.

## What's Exciting for Chess Players

- **"Why is this the best move?"** answered with computed evidence, not vibes or templates
- **Critical moments explained by their MRE signature** — "this was a material-initiative swing" vs "this was a structural transformation" — each moment has a computed explanatory fingerprint
- **Game stories** that trace the causal thread through the whole game, grounded in measured feature transitions
- **Coach-style narratives** constrained to be chess-accurate because the feature selection is computed, not hallucinated
- **Explaining away** means concise explanations — only the features that genuinely matter, not a wall of every possible observation

## Honest Caveat

We haven't proven (via ablation) that the computed constraints actually produce BETTER narratives than an unconstrained LLM. An unconstrained Claude analyzing a chess position might produce equally good prose. The ablation study is the make-or-break experiment. But the architecture is in place — and if the ablation confirms that MRE-constrained narratives are more accurate and consistent, this is a genuine contribution to both chess tools and XAI methodology.

The discomfort heuristic applies: we're excited about this, which means we should be extra careful about what we claim vs. what we've proven.
