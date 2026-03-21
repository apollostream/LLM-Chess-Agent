# Most Relevant Explanation (MRE) Feasibility Assessment

Assessing the feasibility of applying Yuan et al.'s Most Relevant Explanation (MRE) framework to our chess feature Bayesian network for computed implicative reasoning chains.

**Paper:** Yuan, Lim, & Lu. "Most Relevant Explanation in Bayesian Networks." *Journal of Artificial Intelligence Research* 42 (2011): 309-352. [arXiv:1401.3893](https://arxiv.org/abs/1401.3893)

## What MRE Is

MRE finds a **partial instantiation** of target variables that maximizes the **Generalized Bayes Factor (GBF)** as the best explanation for observed evidence. Unlike MAP/MPE which assign values to ALL target variables (overspecified) or singleton methods (underspecified), MRE automatically identifies only the **most relevant** variables.

### The Generalized Bayes Factor

```
GBF(x, e) = P(e|x) / P(e|¬x)

where:
  P(e|¬x) = (P(e) - P(e|x)·P(x)) / (1 - P(x))
```

GBF measures how much more likely the evidence is given the explanation x than given NOT-x. This is the proper Bayes factor form — NOT the simple likelihood ratio P(e|x)/P(e).

**Why the distinction matters:** A common explanation (high P(x)) needs a much stronger association with the evidence to achieve a high GBF, because P(e|¬x) is already close to P(e) when x is common. This naturally produces concise explanations — only variables that genuinely shift the evidence probability survive.

### Conditional Bayes Factor (CBF)

CBF is the GBF of a new explanation conditioned on an existing explanation. It provides a soft measure of variable relevance given what's already explained. This enables:
- **Automatic pruning**: variables that don't increase GBF are excluded
- **Explaining away**: if one variable already explains the evidence, adding another redundant variable doesn't help

### Key Properties

- MRE produces explanations that are both **precise** and **concise**
- CBF captures the **explaining-away** phenomenon native to Bayesian networks
- Dominance relations between candidate solutions yield **diverse top-k** explanations
- MRE is applicable to both causal and non-causal settings

### Computational Complexity

- MRE is **NP-hard** (decision version: NP^PP-complete)
- Exact algorithms: breadth-first branch-and-bound with upper bounds on GBF
- Approximate algorithms: hierarchical beam search (polynomial)
- MRE requires **discrete** variables with conditional probability tables (CPTs)

## Mapping to Our Chess Application

| MRE Concept | Circuit Example (Yuan) | Our Chess Application |
|---|---|---|
| **Evidence (e)** | Output = current | d_eval_stm = "improvement" (from Stockfish) |
| **Target variables (T)** | Gates: {defective, ok} | Feature deltas: {positive, zero, negative} |
| **MRE query** | Which gates most relevantly explain current? | Which feature changes most relevantly explain eval improvement? |
| **Network** | Diagnostic circuit BN | DAG from precision matrix + eval node |
| **MRE output** | {B=defective, C=defective} | {initiative_stm=positive, fork_threats_stm=positive} |

### Why This Mapping Is Natural

- **Evidence = eval change**: What Stockfish tells us (the hypothesis about move quality)
- **Target variables = feature deltas**: What our pipeline computes deterministically (imbalances, tactical motifs)
- **MRE = computed implication chain**: The statistically most relevant subset of feature changes that explains the eval change — computed from the BN, not from LLM prose
- **Explaining away**: If material gain already explains the eval improvement, space gain is automatically pruned — exactly the behavior we want

### What MRE Gives Us That We Don't Have

1. **Principled variable selection** — Instead of the LLM choosing which features to mention, MRE identifies the statistically most relevant subset. Eliminates "errors of construction" at the evidence selection level.
2. **Explaining away** — Redundant features automatically pruned. Our current pipeline presents ALL features and lets the LLM sort it out.
3. **Multiple ranked explanations** — Dominance relations find diverse top-k: "Eval improved because initiative increased (GBF=3.2), OR because material was gained (GBF=2.8)."
4. **Computed Level 1 mechanism rules** — MRE explanations fill the gap between evidence (Level 0) and outcome prediction (Level 3).

### What MRE Does NOT Give Us

1. **Strategic plans (Level 2)** — MRE says WHICH features are relevant, not WHAT PLAN they serve. "Initiative increased" ≠ "kingside attack."
2. **Natural language** — MRE outputs partial variable assignments. The LLM translates them to prose.
3. **Causal claims** — MRE operates on statistical relevance (GBF), not causal mechanisms. Consistent with our "implicative reasoning, not natural causality" framing.

## Expanded Feature Set: Spatial Context Nodes

The original 72 delta features are board-aggregate — `fork_threats_stm = 2` doesn't say WHERE the forks are. To enable MRE to produce spatially-grounded explanations, we add 9 static (positional) context nodes to the BN alongside the 72 delta nodes.

### 5 Regional Control Nodes

Each captures which side controls a 4x4 region of the board. Computed from `piece_activity.squares_attacked` filtered by region. Ternary: opp controls majority (-1), roughly equal (0), stm controls majority (+1).

Non-overlapping region definitions (STM-relative):

All regions are defined from the **side-to-move's perspective**. When STM is White, ranks are as-is (rank 1 = White's back rank). When STM is Black, ranks are **flipped**: Black's back rank (absolute rank 8) becomes STM rank 1, and absolute rank 1 becomes STM rank 8. Files are not flipped (a-file is always a-file). This ensures the same region encoding regardless of which side is moving, consistent with `vectorize_stm()`.

```
  STM-relative board (STM's rank 1 is always STM's back rank):

         a  b  c  |  d  e  |  f  g  h
    8   [opp_qs   ]        [opp_ks   ]     ← OPP's home territory
    7   [         ]        [         ]
    6   [         ]        [         ]
        ----------+ center +----------
    5              [       ]
    4              [       ]
    3              [       ]
        ----------+--------+----------
    2   [stm_qs   ]        [stm_ks   ]     ← STM's home territory
    1   [         ]        [         ]

  center:        files d,e × STM-ranks 3,4,5,6  (8 squares — central zone)
  stm_kingside:  files f,g,h × STM-ranks 1,2,3  (9 squares — STM's kingside corner)
  stm_queenside: files a,b,c × STM-ranks 1,2,3  (9 squares — STM's queenside corner)
  opp_kingside:  files f,g,h × STM-ranks 6,7,8  (9 squares — OPP's kingside corner)
  opp_queenside: files a,b,c × STM-ranks 6,7,8  (9 squares — OPP's queenside corner)
```

**Implementation note:** When STM is Black, absolute square a8 maps to STM-relative (a, rank 1), absolute a1 maps to (a, rank 8). The `vectorize_stm()` function already handles the STM/OPP perspective swap for other features; regional control computation must apply the same rank-flip before classifying squares into regions.

Note: "Kingside" = f,g,h files; "Queenside" = a,b,c files. Remaining squares (d,e × STM-ranks 1,2 and 7,8; a-c and f-h × STM-ranks 4,5) fall in transitional zones — unassigned to any region.

### 4 King Location Nodes

Each captures which zone a king occupies. Ternary encoding of file zone and rank zone.

All king locations use **STM-relative ranks** (same rank-flip as regional control):

```
  stm_king_file:  a,b,c → queenside (-1)  |  d,e → center (0)  |  f,g,h → kingside (+1)
  opp_king_file:  a,b,c → queenside (-1)  |  d,e → center (0)  |  f,g,h → kingside (+1)
  stm_king_rank:  STM-ranks 6,7,8 → advanced into opp territory (-1)  |  STM-ranks 3,4,5 → center (0)  |  STM-ranks 1,2 → home (+1)
  opp_king_rank:  STM-ranks 1,2,3 → advanced into stm territory (-1)  |  STM-ranks 4,5 → center (0)    |  STM-ranks 6,7,8 → home (+1)
```

**Implementation note:** When STM is White, the White king on g1 → stm_king_file=kingside(+1), stm_king_rank=home(+1). When STM is Black, the Black king on g8 → absolute rank 8 flips to STM-rank 1 → stm_king_file=kingside(+1), stm_king_rank=home(+1). Same encoding regardless of color — consistent with `vectorize_stm()`.

King location captures information our current features don't encode:
- King centralization in endgames (king on e4 = active, not unsafe)
- Attack direction (fork threats + opp_king_file=kingside → kingside attack)
- Whether the king is exposed vs. well-placed (context for king_safety features)

### Complete BN Node Set

```
Delta nodes (72):    what changed this move (ternary: positive/zero/negative)
Context nodes (9):   spatial state at P₀ (ternary: stm/neutral/opp or zone encoding)
Target node (1):     d_eval_stm (ternary: improvement/neutral/decline)
                     ──
Total:               82 BN nodes
```

Both delta and context nodes are target variables in MRE. Evidence is the eval change. MRE finds the partial assignment across BOTH that maximizes GBF — naturally producing spatially-grounded explanations like:

```
{d_initiative_stm=positive, d_fork_threats_stm=positive, opp_king_file=kingside}
→ "Initiative and fork threats increased, directed at the kingside where the opponent's king sits"
```

### Empirical Validation of Spatial Nodes

Rather than assuming regional/king nodes help, add them to the feature vector and rerun the Graphical Lasso. The precision matrix will reveal:
- If regional control connects to tactical motifs → spatial context is load-bearing
- If king location connects to king_safety or tactical motifs → king position matters
- If any are degree-0 → drop them from the BN (conditionally independent of everything)

28K data points for 82 features is comfortable for Graphical Lasso estimation.

## Implementation Pipeline

```
Step 1: Add 9 spatial context features to imbalance_vectorizer.py
    ↓
Step 2: Rerun extract_features.py → 82-feature CSV (28K rows)
    ↓
Step 3: Rerun Graphical Lasso → new precision matrix
         Check: do spatial nodes have non-zero edges?
    ↓
Step 4: Orient edges via PC algorithm → DAG (pgmpy)
    ↓
Step 5: Add eval_delta node as child connected to hub features
    ↓
Step 6: Discretize all features to ternary
    ↓
Step 7: Learn CPTs from 28K discretized transitions
    ↓
Step 8: MRE inference: Given e={d_eval_stm=improvement},
         find x* maximizing GBF(x*, e)
    ↓
Output: Spatially-grounded computed most relevant explanation
```

## Challenges (Honest Assessment)

### 1. Computational (Manageable)
MRE is NP-hard, but our network is small (~82 nodes) and sparse (expected ~94% given Graphical Lasso). Yuan et al. tested on comparable networks (Alarm: 37 nodes, Hailfinder: 56, Pathfinder: 135). Beam search approximation should be tractable.

### 2. DAG Orientation (Requires Domain Knowledge)
The precision matrix gives an undirected skeleton. PC algorithm orients some edges via v-structures, but many may remain undirected (CPDAG). Need:
- Domain knowledge for ambiguous edges (material change → tactical motif change, not reverse)
- Temporal ordering from PV replays (feature at ply 1 → feature at ply 3)
- Sensitivity analysis: do MRE explanations change under different valid DAG completions?

### 3. Discretization (Design Choice)
Ternary {positive, zero, negative} loses magnitude information. A +1 pawn gain and +9 queen gain both become "positive." Options:
- 5-level: {strong_negative, negative, zero, positive, strong_positive}
- Per-feature thresholds (0.5 std, 1 std, 2 std)
- Start with ternary, evaluate whether finer granularity adds value

### 4. CPT Estimation (Feasible)
72 ternary nodes with sparse DAG. Most nodes have few parents. Hub nodes (degree 14 for material) have more parent configurations. 28K data points is sufficient with Bayesian parameter estimation (Dirichlet priors for smoothing).

### 5. No Off-the-Shelf MRE (Engineering Effort)
pgmpy supports BN construction, PC algorithm, and standard inference (variable elimination, MAP). Does NOT implement MRE. Need to:
- Implement GBF computation on top of pgmpy inference
- Implement branch-and-bound or beam search
- ~500-1000 lines of code, but algorithms are well-documented

### 6. Validation (Essential)
Do MRE explanations make chess sense? The explaining-away property could prune features a coach considers important context. Must compare MRE outputs against expert assessments.

## Comparison: Decision Tree Rules vs. MRE

| Dimension | Decision Tree (current) | MRE (proposed) |
|---|---|---|
| Variable selection | Fixed by tree structure | Automatic per-query — different positions get different relevant variables |
| Threshold handling | Hard binary splits (>3.5) | Ternary categories with GBF-based relevance |
| Compound effects | Limited by tree depth | Arbitrary subsets via GBF optimization |
| Explaining away | No — tree can't prune redundant variables | Yes — core feature |
| Multiple explanations | One rule per leaf | Diverse top-k via dominance relations |
| Computational cost | O(1) — walk the tree | NP-hard exact, polynomial beam search |
| Interpretability | IF/THEN rules | Partial variable assignments — needs LLM translation |

## Verdict

**MRE is the right approach for Phase 2-3 of the implicative chain roadmap.** The mapping is natural, the theory is sound, the computational challenges are manageable for our network size, and it solves exactly the problem we identified: computed implication chains that the LLM must follow, rather than unconstrained prose.

**Estimated effort**: 2-3 weeks focused work.
- BN construction (PC algorithm + CPTs): ~3 days
- MRE implementation (GBF + beam search): ~5 days
- Validation: ongoing

**Discomfort check**: The main risk is that MRE explanations, while statistically optimal, might not map to chess-meaningful narratives. The explaining-away property could prune features that provide important context. This is testable and must be tested before claiming it works.

## References

- [Yuan et al. (2011). Most Relevant Explanation in Bayesian Networks. JAIR 42:309-352](https://arxiv.org/abs/1401.3893)
- [Yuan & Lu (2015). An Exact Algorithm for Solving MRE. AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/9686)
- [Yuan (2017). Hierarchical Beam Search for Solving MRE. J. Applied Logic](https://www.sciencedirect.com/science/article/pii/S1570868316300854)
- [MRE Computational Complexity. Annals of Mathematics and AI](https://link.springer.com/article/10.1007/s10472-011-9260-z)
- [pgmpy PC Algorithm](https://pgmpy.org/structure_estimator/pc.html)
- [Graphical Lasso + BN Explainability (2024)](https://link.springer.com/chapter/10.1007/978-3-031-78255-8_2)
