#!/usr/bin/env python3
"""Extract implicative rules from trained models on chess feature data.

Surfaces mechanism rules (Level 1) that the GBR has implicitly learned:
IF feature_deltas match pattern THEN eval changes in direction X.

Usage:
    python rule_extraction.py cross-validate [--mode stm] [--splits 5]
    python rule_extraction.py extract-rules [--mode stm] [--depth 4] [--output PATH]
    python rule_extraction.py phase-analysis [--mode stm] [--depth 4] [--output PATH]
    python rule_extraction.py summary --input rules.json [--output report.md] [--top 20]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

ANALYSIS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "analysis"

# Delta columns to exclude from features (leaky or non-informative)
_EXCLUDE_DELTAS = {
    "d_eval_stm", "d_eval_cp", "d_eval_advantage",
    "d_game_phase", "d_is_check",
    "d_side_to_move", "d_total_non_pawn_material",
}

# Target column per mode
_TARGET_COL = {
    "stm": "d_eval_stm",
    "game": "d_eval_cp",
}

# CSV file per mode
_CSV_FILE = {
    "stm": "features_stm.csv",
    "game": "features_game.csv",
}


# ── Data structures ─────────────────────────────────────────────────────────

@dataclass
class Condition:
    feature: str
    operator: str  # "<=" or ">"
    threshold: float


@dataclass
class Rule:
    rule_id: str
    antecedent: list[Condition]
    consequent_class: str
    confidence: float
    coverage: float
    support: int
    lift: float
    phase_stability: dict[str, float] | None = None


@dataclass
class RuleSet:
    source: str
    target: str
    dataset: str
    n_rules: int
    tree_depth: int
    tree_accuracy: float
    rules: list[Rule]
    cross_validation: dict | None = None


# ── Data loading ─────────────────────────────────────────────────────────────

def load_dataset(mode: str = "stm", csv_path: Path | None = None) -> pd.DataFrame:
    """Load features CSV."""
    if csv_path is None:
        csv_path = ANALYSIS_DIR / _CSV_FILE[mode]
    return pd.read_csv(csv_path)


def prepare_features(
    df: pd.DataFrame, mode: str = "stm"
) -> tuple[np.ndarray, np.ndarray, list[str], pd.Series]:
    """Extract X (delta features), y (eval change), feature_names, groups (game_id).

    Drops rows where y is NaN (first position per game has no delta).
    """
    target_col = _TARGET_COL[mode]

    # Select delta columns as features
    delta_cols = [c for c in df.columns if c.startswith("d_") and c not in _EXCLUDE_DELTAS]
    delta_cols = sorted(delta_cols)

    # Drop rows with NaN target
    mask = df[target_col].notna()
    df_clean = df[mask].copy()

    X = df_clean[delta_cols].fillna(0).values
    y = df_clean[target_col].values
    groups = df_clean["game_id"]
    return X, y, delta_cols, groups


def discretize_target(
    y: np.ndarray,
    scheme: str = "3class",
    threshold: float = 50,
) -> tuple[np.ndarray, dict[int, str]]:
    """Discretize continuous eval change into categories.

    3class at ±threshold: decline (<-t), neutral (-t to +t), improvement (>+t)
    5class at ±threshold and ±2*threshold: strong_decline, decline, neutral, improvement, strong_improvement
    """
    if scheme == "3class":
        y_disc = np.where(y > threshold, 2, np.where(y < -threshold, 0, 1)).astype(int)
        label_map = {0: "decline", 1: "neutral", 2: "improvement"}
    elif scheme == "5class":
        t2 = threshold * 2
        y_disc = np.zeros(len(y), dtype=int)
        y_disc[y < -t2] = 0
        y_disc[(y >= -t2) & (y < -threshold)] = 1
        y_disc[(y >= -threshold) & (y <= threshold)] = 2
        y_disc[(y > threshold) & (y <= t2)] = 3
        y_disc[y > t2] = 4
        label_map = {
            0: "strong_decline", 1: "decline", 2: "neutral",
            3: "improvement", 4: "strong_improvement",
        }
    else:
        raise ValueError(f"Unknown scheme: {scheme}")
    return y_disc, label_map


# ── Cross-validation ────────────────────────────────────────────────────────

def cross_validate_model(
    X: np.ndarray,
    y: np.ndarray,
    groups: pd.Series | np.ndarray,
    n_splits: int = 5,
) -> dict:
    """GroupKFold cross-validation of GBR, preventing game leakage."""
    gkf = GroupKFold(n_splits=n_splits)
    scores = []

    for train_idx, test_idx in gkf.split(X, y, groups):
        gbr = GradientBoostingRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.1, random_state=42,
        )
        gbr.fit(X[train_idx], y[train_idx])
        r2 = gbr.score(X[test_idx], y[test_idx])
        scores.append(r2)

    # Also train a standalone decision tree for comparison
    dt = DecisionTreeRegressor(max_depth=4, random_state=42)
    dt_scores = []
    for train_idx, test_idx in gkf.split(X, y, groups):
        dt.fit(X[train_idx], y[train_idx])
        dt_scores.append(dt.score(X[test_idx], y[test_idx]))

    unique_groups = np.unique(groups)
    return {
        "mean_r2": float(np.mean(scores)),
        "std_r2": float(np.std(scores)),
        "per_fold_scores": [float(s) for s in scores],
        "n_samples": int(X.shape[0]),
        "n_features": int(X.shape[1]),
        "n_groups": int(len(unique_groups)),
        "decision_tree_mean_r2": float(np.mean(dt_scores)),
        "decision_tree_std_r2": float(np.std(dt_scores)),
        "decision_tree_per_fold": [float(s) for s in dt_scores],
    }


# ── Rule extraction ─────────────────────────────────────────────────────────

def _extract_paths(tree_, node_id=0, path=None):
    """Recursive DFS extracting root-to-leaf paths from sklearn tree_."""
    if path is None:
        path = []

    # Leaf node
    if tree_.children_left[node_id] == -1:
        yield path, node_id
        return

    feature_idx = tree_.feature[node_id]
    threshold = tree_.threshold[node_id]

    # Left child: feature <= threshold
    yield from _extract_paths(
        tree_, tree_.children_left[node_id],
        path + [(feature_idx, "<=", threshold)],
    )
    # Right child: feature > threshold
    yield from _extract_paths(
        tree_, tree_.children_right[node_id],
        path + [(feature_idx, ">", threshold)],
    )


def train_and_extract_rules(
    X: np.ndarray,
    y_disc: np.ndarray,
    feature_names: list[str],
    label_map: dict[int, str],
    max_depth: int = 4,
) -> tuple[DecisionTreeClassifier, list[Rule]]:
    """Train a standalone DecisionTreeClassifier and extract all rules."""
    tree = DecisionTreeClassifier(max_depth=max_depth, random_state=42)
    tree.fit(X, y_disc)

    n_total = len(y_disc)
    n_classes = len(label_map)
    baseline_rates = {c: float(np.sum(y_disc == c)) / n_total for c in label_map}

    rules = []
    for path, leaf_id in _extract_paths(tree.tree_):
        antecedent = [
            Condition(
                feature=feature_names[feat_idx],
                operator=op,
                threshold=round(float(thresh), 4),
            )
            for feat_idx, op, thresh in path
        ]

        # Leaf value: class distribution
        value = tree.tree_.value[leaf_id].flatten()
        n_samples = int(tree.tree_.n_node_samples[leaf_id])
        predicted_class = int(np.argmax(value))
        confidence = float(value[predicted_class] / value.sum()) if value.sum() > 0 else 0.0
        coverage = n_samples / n_total
        baseline = baseline_rates.get(predicted_class, 1.0 / n_classes)
        lift = confidence / baseline if baseline > 0 else 0.0

        rules.append(Rule(
            rule_id=f"leaf_{leaf_id}",
            antecedent=antecedent,
            consequent_class=label_map.get(predicted_class, str(predicted_class)),
            confidence=round(confidence, 4),
            coverage=round(coverage, 4),
            support=n_samples,
            lift=round(lift, 4),
        ))

    return tree, rules


# ── Phase stability ──────────────────────────────────────────────────────────

def _map_game_phase(phase_val) -> str:
    """Map numeric or string game_phase to opening/middlegame/endgame.

    Handles both categorical integers (0/1/2) and continuous floats (0.0-1.0).
    """
    if isinstance(phase_val, str):
        val = phase_val.lower()
        if "open" in val:
            return "opening"
        if "middle" in val:
            return "middlegame"
        return "endgame"
    # Categorical integers: 0=opening, 1=middlegame, 2=endgame
    if isinstance(phase_val, (int, np.integer)) or (isinstance(phase_val, float) and phase_val == int(phase_val) and phase_val <= 2):
        phase_int = int(phase_val)
        return {0: "opening", 1: "middlegame", 2: "endgame"}.get(phase_int, "endgame")
    # Continuous float: 0-0.3 opening, 0.3-0.7 middlegame, 0.7+ endgame
    if phase_val < 0.3:
        return "opening"
    if phase_val < 0.7:
        return "middlegame"
    return "endgame"


def compute_phase_stability(
    rules: list[Rule],
    X: np.ndarray,
    y_disc: np.ndarray,
    phases: np.ndarray,
    label_map: dict[int, str],
) -> list[Rule]:
    """Annotate each rule with per-phase confidence."""
    phase_labels = np.array([_map_game_phase(p) for p in phases])
    unique_phases = sorted(set(phase_labels))

    for rule in rules:
        # Evaluate antecedent mask on full data
        mask = np.ones(len(X), dtype=bool)
        for cond in rule.antecedent:
            feat_idx = None
            # Find feature index — we need feature_names but don't have it here
            # Use a workaround: match by column count
            # Actually, we store the feature name in cond, but need to map to X column
            # This function should be called with feature_names available
            # For now, skip if we can't resolve
            pass

        # Simpler approach: use tree prediction
        # Re-evaluate: for each phase, what fraction of samples matching this rule's
        # predicted class actually match?
        stability = {}
        for phase in unique_phases:
            phase_mask = phase_labels == phase
            if phase_mask.sum() == 0:
                stability[phase] = 0.0
                continue

            # Apply antecedent conditions to phase subset
            X_phase = X[phase_mask]
            y_phase = y_disc[phase_mask]
            if len(X_phase) == 0:
                stability[phase] = 0.0
                continue

            # Evaluate antecedent on this phase's data
            ant_mask = np.ones(len(X_phase), dtype=bool)
            for cond in rule.antecedent:
                # We need feature index — rebuild from feature name
                # This is a design issue; fix by passing feature_names
                pass

            stability[phase] = 0.0  # placeholder

        rule.phase_stability = stability

    return rules


def compute_phase_stability_with_names(
    rules: list[Rule],
    X: np.ndarray,
    y_disc: np.ndarray,
    phases: np.ndarray,
    label_map: dict[int, str],
    feature_names: list[str],
) -> list[Rule]:
    """Annotate each rule with per-phase confidence (with feature name resolution)."""
    phase_labels = np.array([_map_game_phase(p) for p in phases])
    unique_phases = sorted(set(phase_labels))

    # Build feature name → index map
    feat_idx_map = {name: i for i, name in enumerate(feature_names)}

    predicted_class_map = {v: k for k, v in label_map.items()}

    for rule in rules:
        stability = {}
        pred_class = predicted_class_map.get(rule.consequent_class)

        for phase in unique_phases:
            phase_mask = phase_labels == phase
            X_phase = X[phase_mask]
            y_phase = y_disc[phase_mask]
            if len(X_phase) == 0:
                stability[phase] = 0.0
                continue

            # Apply antecedent conditions
            ant_mask = np.ones(len(X_phase), dtype=bool)
            for cond in rule.antecedent:
                idx = feat_idx_map.get(cond.feature)
                if idx is None:
                    continue
                if cond.operator == "<=":
                    ant_mask &= X_phase[:, idx] <= cond.threshold
                else:
                    ant_mask &= X_phase[:, idx] > cond.threshold

            n_matching = ant_mask.sum()
            if n_matching == 0:
                stability[phase] = 0.0
                continue

            if pred_class is not None:
                n_correct = (y_phase[ant_mask] == pred_class).sum()
                stability[phase] = round(float(n_correct / n_matching), 4)
            else:
                stability[phase] = 0.0

        rule.phase_stability = stability

    return rules


# ── Phase analysis ───────────────────────────────────────────────────────────

def phase_analysis(
    df: pd.DataFrame,
    mode: str = "stm",
    max_depth: int = 4,
    scheme: str = "3class",
    threshold: float = 50,
) -> dict[str, RuleSet]:
    """Train separate trees per game phase and identify universal rules."""
    X, y, feature_names, groups = prepare_features(df, mode)
    y_disc, label_map = discretize_target(y, scheme=scheme, threshold=threshold)

    # Map phases
    phase_col = df.loc[df[_TARGET_COL[mode]].notna(), "game_phase"].values
    phase_labels = np.array([_map_game_phase(p) for p in phase_col])

    result = {}

    # Per-phase trees
    for phase in ["opening", "middlegame", "endgame"]:
        mask = phase_labels == phase
        if mask.sum() < 50:
            continue
        X_phase = X[mask]
        y_phase = y_disc[mask]

        tree, rules = train_and_extract_rules(
            X_phase, y_phase, feature_names, label_map, max_depth=max_depth,
        )
        accuracy = float(tree.score(X_phase, y_phase))
        result[phase] = RuleSet(
            source=f"{mode}_decision_tree_{phase}",
            target=_TARGET_COL[mode],
            dataset=mode,
            n_rules=len(rules),
            tree_depth=max_depth,
            tree_accuracy=accuracy,
            rules=rules,
        )

    # All-data tree with phase stability
    tree_all, rules_all = train_and_extract_rules(
        X, y_disc, feature_names, label_map, max_depth=max_depth,
    )
    rules_all = compute_phase_stability_with_names(
        rules_all, X, y_disc, phase_labels, label_map, feature_names,
    )
    accuracy_all = float(tree_all.score(X, y_disc))
    result["all"] = RuleSet(
        source=f"{mode}_decision_tree_all",
        target=_TARGET_COL[mode],
        dataset=mode,
        n_rules=len(rules_all),
        tree_depth=max_depth,
        tree_accuracy=accuracy_all,
        rules=rules_all,
    )

    return result


# ── Output formatting ────────────────────────────────────────────────────────

def format_condition(cond: Condition) -> str:
    """Human-readable condition string."""
    return f"{cond.feature} {cond.operator} {cond.threshold}"


def format_rule(rule: Rule) -> str:
    """Full IF...THEN string with metrics."""
    conditions = " AND ".join(format_condition(c) for c in rule.antecedent)
    line = f"IF {conditions}\n   THEN {rule.consequent_class}"
    line += f" (confidence: {rule.confidence}, coverage: {rule.coverage}, lift: {rule.lift})"
    if rule.phase_stability:
        parts = [f"{k}={v}" for k, v in sorted(rule.phase_stability.items())]
        max_diff = max(rule.phase_stability.values()) - min(rule.phase_stability.values()) if rule.phase_stability else 0
        tag = "universal" if max_diff < 0.10 else ("phase-dependent" if max_diff > 0.20 else "moderate")
        line += f"\n   Stability: {' '.join(parts)} [{tag}]"
    return line


def rules_to_json(rule_set: RuleSet) -> dict:
    """Serialize RuleSet to JSON-compatible dict."""
    return {
        "source": rule_set.source,
        "target": rule_set.target,
        "dataset": rule_set.dataset,
        "n_rules": rule_set.n_rules,
        "tree_depth": rule_set.tree_depth,
        "tree_accuracy": rule_set.tree_accuracy,
        "cross_validation": rule_set.cross_validation,
        "rules": [
            {
                "rule_id": r.rule_id,
                "antecedent": [
                    {"feature": c.feature, "operator": c.operator, "threshold": c.threshold}
                    for c in r.antecedent
                ],
                "consequent_class": r.consequent_class,
                "confidence": r.confidence,
                "coverage": r.coverage,
                "support": r.support,
                "lift": r.lift,
                "phase_stability": r.phase_stability,
            }
            for r in rule_set.rules
        ],
    }


def rules_to_markdown(rule_set: RuleSet, top_n: int = 20) -> str:
    """Render top rules as readable markdown report."""
    lines = []
    lines.append(f"# Extracted Rules: {rule_set.source}")
    lines.append("")
    lines.append(f"- **Dataset**: {rule_set.dataset}")
    lines.append(f"- **Target**: {rule_set.target}")
    lines.append(f"- **Tree depth**: {rule_set.tree_depth}")
    lines.append(f"- **Tree accuracy**: {rule_set.tree_accuracy:.4f}")
    lines.append(f"- **Total rules**: {rule_set.n_rules}")
    if rule_set.cross_validation:
        cv = rule_set.cross_validation
        lines.append(f"- **GBR GroupKFold R²**: {cv['mean_r2']:.4f} ± {cv['std_r2']:.4f}")
        if "decision_tree_mean_r2" in cv:
            lines.append(f"- **Decision tree GroupKFold R²**: {cv['decision_tree_mean_r2']:.4f} ± {cv['decision_tree_std_r2']:.4f}")
    lines.append("")

    # Sort by confidence * coverage (balanced metric)
    sorted_rules = sorted(
        rule_set.rules,
        key=lambda r: r.confidence * r.coverage,
        reverse=True,
    )[:top_n]

    lines.append(f"## Top {min(top_n, len(sorted_rules))} Rules (by confidence × coverage)")
    lines.append("")

    for i, rule in enumerate(sorted_rules, 1):
        lines.append(f"### Rule {i} ({rule.rule_id})")
        lines.append("```")
        lines.append(format_rule(rule))
        lines.append("```")
        lines.append(f"Support: {rule.support} positions")
        lines.append("")

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────────

def cmd_cross_validate(args):
    """Cross-validate GBR model with GroupKFold."""
    print(f"Loading {args.mode} dataset...", file=sys.stderr)
    df = load_dataset(mode=args.mode)
    X, y, feature_names, groups = prepare_features(df, mode=args.mode)
    print(f"Dataset: {X.shape[0]} rows × {X.shape[1]} features, {len(np.unique(groups))} games", file=sys.stderr)

    print(f"Running {args.splits}-fold GroupKFold cross-validation...", file=sys.stderr)
    result = cross_validate_model(X, y, groups, n_splits=args.splits)

    print(f"GBR mean R² = {result['mean_r2']:.4f} ± {result['std_r2']:.4f}", file=sys.stderr)
    print(f"DT  mean R² = {result['decision_tree_mean_r2']:.4f} ± {result['decision_tree_std_r2']:.4f}", file=sys.stderr)

    json.dump(result, sys.stdout, indent=2)
    print()


def cmd_extract_rules(args):
    """Extract rules from a standalone decision tree."""
    print(f"Loading {args.mode} dataset...", file=sys.stderr)
    df = load_dataset(mode=args.mode)
    X, y, feature_names, groups = prepare_features(df, mode=args.mode)
    y_disc, label_map = discretize_target(y, scheme=args.scheme, threshold=args.threshold)

    class_dist = {label_map[c]: int(np.sum(y_disc == c)) for c in label_map}
    print(f"Class distribution: {class_dist}", file=sys.stderr)

    print(f"Training DecisionTreeClassifier (max_depth={args.depth})...", file=sys.stderr)
    tree, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=args.depth)
    accuracy = float(tree.score(X, y_disc))
    print(f"Tree accuracy: {accuracy:.4f}, {len(rules)} rules extracted", file=sys.stderr)

    # Phase stability
    phase_col = df.loc[df[_TARGET_COL[args.mode]].notna(), "game_phase"].values
    rules = compute_phase_stability_with_names(
        rules, X, y_disc, phase_col, label_map, feature_names,
    )

    # Cross-validate for comparison (optional, slow on large datasets)
    cv_result = None
    if not args.no_cv:
        print(f"Cross-validating for comparison...", file=sys.stderr)
        cv_result = cross_validate_model(X, y, groups, n_splits=min(5, len(np.unique(groups))))

    rule_set = RuleSet(
        source=f"{args.mode}_decision_tree",
        target=_TARGET_COL[args.mode],
        dataset=args.mode,
        n_rules=len(rules),
        tree_depth=args.depth,
        tree_accuracy=accuracy,
        rules=rules,
        cross_validation=cv_result,
    )

    output_data = rules_to_json(rule_set)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output_data, indent=2))
        print(f"Rules written to {output_path}", file=sys.stderr)
    else:
        json.dump(output_data, sys.stdout, indent=2)
        print()


def cmd_phase_analysis(args):
    """Per-phase model training and universal rule detection."""
    print(f"Loading {args.mode} dataset...", file=sys.stderr)
    df = load_dataset(mode=args.mode)

    result = phase_analysis(df, mode=args.mode, max_depth=args.depth)

    output_data = {phase: rules_to_json(rs) for phase, rs in result.items()}

    # Summary
    for phase, rs in result.items():
        print(f"  {phase}: {rs.n_rules} rules, accuracy={rs.tree_accuracy:.4f}", file=sys.stderr)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output_data, indent=2))
        print(f"Phase analysis written to {output_path}", file=sys.stderr)
    else:
        json.dump(output_data, sys.stdout, indent=2)
        print()


def cmd_summary(args):
    """Render markdown summary from rules JSON."""
    input_path = Path(args.input)
    data = json.loads(input_path.read_text())

    # Reconstruct RuleSet
    rules = []
    for r in data["rules"]:
        rules.append(Rule(
            rule_id=r["rule_id"],
            antecedent=[Condition(**c) for c in r["antecedent"]],
            consequent_class=r["consequent_class"],
            confidence=r["confidence"],
            coverage=r["coverage"],
            support=r["support"],
            lift=r["lift"],
            phase_stability=r.get("phase_stability"),
        ))

    rule_set = RuleSet(
        source=data["source"],
        target=data["target"],
        dataset=data["dataset"],
        n_rules=data["n_rules"],
        tree_depth=data["tree_depth"],
        tree_accuracy=data["tree_accuracy"],
        rules=rules,
        cross_validation=data.get("cross_validation"),
    )

    md = rules_to_markdown(rule_set, top_n=args.top)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md)
        print(f"Report written to {output_path}", file=sys.stderr)
    else:
        print(md)


def main():
    parser = argparse.ArgumentParser(
        description="Extract implicative rules from chess feature models",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # cross-validate
    p_cv = subparsers.add_parser("cross-validate", help="GroupKFold cross-validation of GBR")
    p_cv.add_argument("--mode", default="stm", choices=["stm", "game"])
    p_cv.add_argument("--splits", type=int, default=5)
    p_cv.set_defaults(func=cmd_cross_validate)

    # extract-rules
    p_extract = subparsers.add_parser("extract-rules", help="Extract rules from decision tree")
    p_extract.add_argument("--mode", default="stm", choices=["stm", "game"])
    p_extract.add_argument("--depth", type=int, default=4)
    p_extract.add_argument("--scheme", default="3class", choices=["3class", "5class"])
    p_extract.add_argument("--threshold", type=float, default=50)
    p_extract.add_argument("--output", type=str, default=None)
    p_extract.add_argument("--no-cv", action="store_true", help="Skip cross-validation (faster)")
    p_extract.set_defaults(func=cmd_extract_rules)

    # phase-analysis
    p_phase = subparsers.add_parser("phase-analysis", help="Per-phase rule extraction")
    p_phase.add_argument("--mode", default="stm", choices=["stm", "game"])
    p_phase.add_argument("--depth", type=int, default=4)
    p_phase.add_argument("--output", type=str, default=None)
    p_phase.set_defaults(func=cmd_phase_analysis)

    # summary
    p_summary = subparsers.add_parser("summary", help="Render markdown from rules JSON")
    p_summary.add_argument("--input", required=True, type=str)
    p_summary.add_argument("--output", type=str, default=None)
    p_summary.add_argument("--top", type=int, default=20)
    p_summary.set_defaults(func=cmd_summary)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
