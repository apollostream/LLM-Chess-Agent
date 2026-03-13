# BFIH Chess Analysis Protocol

Mapping the Bayesian Framework for Intellectual Honesty (Rev 4) to chess position analysis. This protocol is activated in **deep mode** and produces a rigorous, multi-paradigm evaluation that surfaces hidden assumptions and resists premature convergence.

---

## Why BFIH for Chess?

Chess evaluation suffers from the same cognitive biases that plague any analytical endeavor: anchoring on first impressions, confirmation bias toward the "obvious" assessment, paradigm blindness (seeing only positional or only tactical possibilities), and motivated reasoning (preferring assessments that validate our style). The BFIH framework forces structured discomfort with our initial read.

---

## Phase 1: Pre-Analysis (State K₀)

Before examining the position, explicitly state your priors:

### K₀ Declaration

1. **Opening context:** What opening or structure does this arise from? What are the typical plans and themes? If unknown, state that.
2. **Paradigm identification:** Am I approaching this as a positional player, a tactician, a universal player? What does my natural inclination tell me about the position at first glance?
3. **Initial impression (gut read):** In one sentence, who do I think stands better and why? This is the hypothesis I must now test — and the one I must be most suspicious of.
4. **Confidence level:** How confident am I in this initial read? (Use rough scale: speculative / moderate / confident / very confident)
5. **What would change my mind:** Identify 1-2 specific findings that would cause me to revise my initial assessment.

**Template:**
```
### K₀ — Initial State
- **Context:** [Opening/structure identification]
- **Paradigm:** [Positional / Dynamic / Universal — how am I approaching this?]
- **Gut read:** [One-sentence initial assessment]
- **Confidence:** [speculative / moderate / confident / very confident]
- **Disconfirming triggers:** [What would change my mind]
```

---

## Phase 2: Hypothesis Generation

Formulate 2-4 competing evaluations of the position as MECE hypotheses (Mutually Exclusive, Collectively Exhaustive).

### Requirements

- At least one hypothesis must challenge the K₀ gut read
- Include a "catch-all" hypothesis for anything not captured by the main hypotheses
- Assign initial prior probabilities (must sum to 1.0)
- Each hypothesis should specify: who stands better, why, and what the correct plan is

### Example Hypotheses

```
H1 (0.45): White is clearly better — superior pawn structure gives lasting advantage
H2 (0.30): Position is dynamically balanced — Black's piece activity compensates for structural defects
H3 (0.15): Black has hidden resources — the initiative/attack provides full compensation
H_catch (0.10): The position is more complex than captured above — requires deeper tactical analysis
```

---

## Ontological Scan (The 10-Imbalance Systematic Check)

This is the chess equivalent of the BFIH 7-domain scan. Check all 10 imbalance categories from `imbalances_guide.md`:

1. Superior Minor Piece
2. Pawn Structure
3. Space
4. Material
5. Control of Key File
6. Control of Hole / Weak Square
7. Lead in Development
8. Initiative
9. King Safety
10. Statics vs Dynamics

For each category, note:
- **Finding:** What does the board_utils data show?
- **Relevance:** How important is this imbalance in the current position? (high / moderate / low)
- **Direction:** Which side benefits?
- **Interaction:** How does this imbalance interact with others?

**Do not skip categories.** The whole point is to prevent the tunnel vision of focusing only on the "obvious" imbalances.

---

## Ancestral Check

How have similar positions been evaluated historically? This is the chess equivalent of checking whether your reasoning follows a well-worn path or breaks new ground.

### Questions to Ask

1. **Structural analogy:** What known pawn structures does this resemble? (Carlsbad, IQP, Hedgehog, King's Indian pawn chain, etc.) What are the established principles for those structures?
2. **Paradigm precedent:** Would a Petrosian (prophylactic, positional) evaluate this differently than a Tal (dynamic, sacrificial)? A Karpov (squeeze) differently than a Kasparov (initiative)?
3. **Engine vs human:** Would a human master's assessment differ from an engine's? Where and why?
4. **Historical pitfalls:** Are there known cases where this type of position was mis-evaluated? What caused the error?

---

## Paradigm Inversion

**This is the core BFIH move applied to chess.** Force yourself to argue the opposite of your initial assessment.

### Protocol

1. **If K₀ favors White:** Construct the strongest possible case for Black. What dynamic resources exist? What counterplay is available? What would a player who *specializes* in Black's position type see that you're missing?
2. **If K₀ is positional:** Reread the position through purely dynamic/tactical eyes. Are there sacrificial possibilities? Does the initiative matter more than structure here?
3. **If K₀ is tactical:** Reread through positional eyes. After the tactics resolve, who has the better long-term position? Is the attack actually dangerous, or is it sound and fury?

### Quality Check

The paradigm inversion is insufficient if:
- It was easy to dismiss (you weren't genuinely uncomfortable)
- It didn't surface at least one consideration you initially overlooked
- It didn't move your probability estimates at all

If any of these are true, **try harder**. The discomfort heuristic applies: if the inversion felt comfortable, it wasn't a real inversion.

---

## Phase 3: Evidence Matrix

Map each imbalance finding to each hypothesis using qualitative likelihood ratios.

### Structure

For each imbalance finding, assess: "How likely would we see this finding if H_n were true?"

```
| Imbalance Finding       | H1 (White better) | H2 (Balanced) | H3 (Black resources) | H_catch |
|------------------------|-------------------|---------------|---------------------|---------|
| White has bishop pair   | Expected (++)     | Possible (+)  | Irrelevant (0)       | ?       |
| Black Nd5 outpost       | Possible (+)      | Expected (++) | Expected (++)        | ?       |
| Open e-file, Black rook | Unlikely (-)      | Expected (++) | Expected (++)        | ?       |
```

Likelihood notation:
- `++` : Strongly expected under this hypothesis
- `+`  : Consistent with this hypothesis
- `0`  : Neutral / irrelevant
- `-`  : Somewhat surprising under this hypothesis
- `--` : Very surprising under this hypothesis

### Update Priors

After filling the matrix, update your hypothesis probabilities. The hypotheses most consistent with the evidence should gain probability mass. Note any hypothesis whose probability changed significantly from the initial prior — this is where your K₀ was challenged.

---

## Phase 4: Reflexive Review

### Has the Evidence Challenged K₀?

1. Compare final posteriors to initial priors. If they're nearly identical, ask: "Did I actually update, or did I just confirm my initial read?"
2. Identify the single most surprising finding — the one that most challenged your K₀. How much weight did you give it? Would a different analyst give it more?
3. **Paradigm sensitivity test:** Would a purely positional analyst reach the same conclusion? A purely dynamic one? If they'd disagree, which paradigm is more appropriate for this position type, and why?

### Red Team

State the strongest argument against your current leading hypothesis. If you can't articulate a strong counter-argument, you either haven't looked hard enough or the position really is one-sided (which is rarer than people think).

---

## Phase 5: Synthesis

### What's Robust Across Paradigms

Identify findings and conclusions that hold regardless of whether you approach the position positionally or dynamically. These are your highest-confidence assessments.

### What's Paradigm-Dependent

Identify where the assessment changes depending on paradigm. Be explicit: "A positional reading suggests X, but a dynamic reading suggests Y. The position is more [static/dynamic], so Z gets more weight."

### Final Assessment

```
### Synthesis
- **Assessment:** [Who stands better, by how much: slight / clear / decisive]
- **Confidence:** [How confident, given the analysis: speculative / moderate / confident / very confident]
- **Key imbalances:** [The 2-3 imbalances that matter most and why]
- **Paradigm note:** [Is this assessment robust or paradigm-dependent?]
- **K₀ revision:** [How much did the analysis change the initial gut read? What was learned?]
- **Disconfirming evidence acknowledged:** [What evidence cuts against this assessment?]
```

---

## Discomfort Heuristic

The final check. After completing the analysis, ask:

1. Does this assessment feel comfortable and expected? If yes, the paradigm inversion was likely insufficient.
2. Was there a moment during the analysis where my confidence dropped before recovering? That moment probably contains the most insight.
3. Am I more uncertain now than when I started? Good — that means the analysis revealed genuine complexity rather than papering over it.

The goal is not to always be uncertain, but to be *appropriately* uncertain. Some positions really are clearly better for one side. But the BFIH protocol ensures you've earned that confidence through rigorous analysis rather than assumption.

---

## Deep Mode Output Template

```
## Deep Analysis — [FEN or position description]

### K₀ — Initial State
[Pre-analysis declaration]

### Hypotheses
[2-4 competing evaluations with priors]

### Ontological Scan
[All 10 imbalances checked systematically]

### Ancestral Check
[Historical/paradigmatic context]

### Paradigm Inversion
[Forced counter-argument]

### Evidence Matrix
[Imbalance → hypothesis mapping]

### Updated Posteriors
[Revised probabilities with reasoning]

### Reflexive Review
[Red team + paradigm sensitivity]

### Synthesis
[Final assessment with confidence and caveats]

### Candidate Moves
[3-5 moves with strategic rationale tied to the assessed imbalances]
```
