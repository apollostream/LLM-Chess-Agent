#!/usr/bin/env python3
"""Most Relevant Explanation (MRE) inference on chess Bayesian network.

Implements Yuan et al.'s MRE framework: finds the partial instantiation
of target variables maximizing the Generalized Bayes Factor (GBF) as the
best explanation for observed evidence (eval change).

GBF(x, e) = P(e|x) / P(e|¬x)
where P(e|¬x) = (P(e) - P(e|x)·P(x)) / (1 - P(x))

Usage:
    from mre_inference import MREEngine, format_mre_explanation
    engine = MREEngine.from_bif("analysis/chess_bn.bif")
    results = engine.find_mre(evidence={"eval_change": "improvement"})
    for explanation, gbf in results:
        print(format_mre_explanation((explanation, gbf)))
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from pathlib import Path

from pgmpy.inference import VariableElimination
from pgmpy.readwrite import BIFReader


class MREEngine:
    """Most Relevant Explanation engine for chess Bayesian network."""

    def __init__(self, model, evidence_variable: str = "eval_change"):
        self.model = model
        self.infer = VariableElimination(model)
        self.evidence_variable = evidence_variable
        self.target_variables = [
            n for n in model.nodes() if n != evidence_variable
        ]
        # Cache marginal P(e) for each evidence state
        self._p_e_cache: dict[str, float] = {}

    @classmethod
    def from_bif(cls, bif_path: str) -> MREEngine:
        """Load a BN from a BIF file and create an MRE engine."""
        reader = BIFReader(bif_path)
        model = reader.get_model()
        return cls(model)

    def _p_evidence(self, evidence: dict[str, str]) -> float:
        """Compute P(e) — marginal probability of evidence."""
        key = str(sorted(evidence.items()))
        if key not in self._p_e_cache:
            result = self.infer.query(
                list(evidence.keys()),
                show_progress=False,
            )
            # Get probability of the specific evidence state
            p = self._get_prob_from_factor(result, evidence)
            self._p_e_cache[key] = p
        return self._p_e_cache[key]

    def _p_evidence_given_x(self, evidence: dict[str, str],
                             explanation: dict[str, str]) -> float:
        """Compute P(e|x) — probability of evidence given explanation."""
        result = self.infer.query(
            list(evidence.keys()),
            evidence=explanation,
            show_progress=False,
        )
        return self._get_prob_from_factor(result, evidence)

    def _p_x(self, explanation: dict[str, str]) -> float:
        """Compute P(x) — prior probability of explanation."""
        result = self.infer.query(
            list(explanation.keys()),
            show_progress=False,
        )
        return self._get_prob_from_factor(result, explanation)

    def _get_prob_from_factor(self, factor, assignment: dict[str, str]) -> float:
        """Extract P(assignment) from a pgmpy DiscreteFactor."""
        # Build index into the factor's values array
        variables = factor.variables
        state_names = factor.state_names

        idx = []
        for var in variables:
            states = state_names[var]
            target_state = assignment[var]
            if target_state in states:
                idx.append(states.index(target_state))
            else:
                return 0.0

        return float(factor.values[tuple(idx)])

    def compute_gbf(self, explanation: dict[str, str],
                    evidence: dict[str, str]) -> float:
        """Compute Generalized Bayes Factor.

        GBF(x, e) = P(e|x) / P(e|¬x)
        where P(e|¬x) = (P(e) - P(e|x)·P(x)) / (1 - P(x))
        """
        p_e = self._p_evidence(evidence)
        p_e_given_x = self._p_evidence_given_x(evidence, explanation)
        p_x = self._p_x(explanation)

        # P(e|¬x) = (P(e) - P(e|x)·P(x)) / (1 - P(x))
        if p_x >= 1.0 - 1e-10:
            return float('inf') if p_e_given_x > p_e else 0.0

        p_e_given_not_x = (p_e - p_e_given_x * p_x) / (1.0 - p_x)

        if p_e_given_not_x <= 1e-10:
            return float('inf') if p_e_given_x > 0 else 1.0

        return p_e_given_x / p_e_given_not_x

    def _candidate_extensions(self, current: dict[str, str],
                               evidence: dict[str, str]) -> list[tuple[dict, float]]:
        """Generate candidate extensions by adding one variable-state pair."""
        assigned = set(current.keys()) | set(evidence.keys())
        candidates = []

        for var in self.target_variables:
            if var in assigned:
                continue

            # Get possible states for this variable
            states = self.model.get_cpds(var).state_names[var]
            for state in states:
                extended = {**current, var: state}
                try:
                    gbf = self.compute_gbf(extended, evidence)
                    candidates.append((extended, gbf))
                except Exception:
                    continue

        return candidates

    def find_mre(self, evidence: dict[str, str],
                 beam_width: int = 10,
                 top_k: int = 5,
                 max_depth: int = 6) -> list[tuple[dict[str, str], float]]:
        """Find Most Relevant Explanations via beam search.

        Returns list of (explanation, gbf) sorted by GBF descending.
        Each explanation is a partial instantiation of target variables.

        Args:
            evidence: observed variables (e.g., {"eval_change": "improvement"})
            beam_width: number of candidates to keep at each level
            top_k: number of top explanations to return
            max_depth: maximum number of variables in explanation
        """
        # Initialize beam with single-variable explanations
        assigned_vars = set(evidence.keys())
        beam: list[tuple[float, dict[str, str]]] = []

        for var in self.target_variables:
            if var in assigned_vars:
                continue
            states = self.model.get_cpds(var).state_names[var]
            for state in states:
                explanation = {var: state}
                try:
                    gbf = self.compute_gbf(explanation, evidence)
                    if gbf > 1.0:  # only keep explanations better than prior
                        heapq.heappush(beam, (-gbf, id(explanation), explanation))
                except Exception:
                    continue

        # Keep top beam_width
        beam = heapq.nsmallest(beam_width * 3, beam)  # broader initial pool

        # Track best explanations across all depths
        all_results: list[tuple[dict[str, str], float]] = []
        for neg_gbf, _, explanation in beam:
            all_results.append((explanation, -neg_gbf))

        # Iterative deepening
        for depth in range(2, max_depth + 1):
            next_beam: list[tuple[float, int, dict]] = []

            for neg_gbf, _, current in beam[:beam_width]:
                current_gbf = -neg_gbf

                # Try extending with each unassigned variable
                extensions = self._candidate_extensions(current, evidence)
                for extended, ext_gbf in extensions:
                    if ext_gbf > current_gbf:  # only keep if GBF improves
                        heapq.heappush(next_beam, (-ext_gbf, id(extended), extended))
                        all_results.append((extended, ext_gbf))

            if not next_beam:
                break

            beam = heapq.nsmallest(beam_width, next_beam)

        # Deduplicate and sort by GBF
        seen = set()
        unique_results = []
        for explanation, gbf in sorted(all_results, key=lambda x: -x[1]):
            key = tuple(sorted(explanation.items()))
            if key not in seen:
                seen.add(key)
                unique_results.append((explanation, gbf))

        return unique_results[:top_k]


def format_mre_explanation(result: tuple[dict[str, str], float]) -> str:
    """Format an MRE result as human-readable text."""
    explanation, gbf = result
    parts = []
    for var, state in sorted(explanation.items()):
        # Clean up variable name for readability
        display = var.replace("d_", "Δ").replace("_stm", " (STM)").replace("_opp", " (OPP)")
        display = display.replace("region_", "region: ")
        parts.append(f"{display} = {state}")

    return f"GBF={gbf:.2f}: {{{', '.join(parts)}}}"


if __name__ == "__main__":
    import sys
    bif_path = sys.argv[1] if len(sys.argv) > 1 else "analysis/chess_bn.bif"
    evidence_state = sys.argv[2] if len(sys.argv) > 2 else "improvement"

    print(f"Loading BN from {bif_path}...")
    engine = MREEngine.from_bif(bif_path)
    print(f"BN: {len(engine.model.nodes())} nodes, {len(engine.target_variables)} target variables")

    evidence = {"eval_change": evidence_state}
    print(f"\nFinding MRE for evidence: {evidence}")
    results = engine.find_mre(evidence, beam_width=10, top_k=5)

    print(f"\nTop {len(results)} explanations:")
    for i, (explanation, gbf) in enumerate(results, 1):
        print(f"\n  #{i}: {format_mre_explanation((explanation, gbf))}")
