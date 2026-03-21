"""Tests for rule_extraction.py — implicative rule extraction from trained models.

TDD: test structure written before implementation.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

# Add scripts dir to path
SCRIPTS_DIR = Path(__file__).parent.parent / ".claude" / "skills" / "chess-imbalances" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

ANALYSIS_DIR = Path(__file__).parent.parent / "analysis"
FEATURES_STM_CSV = ANALYSIS_DIR / "features_stm.csv"
VENV_PYTHON = Path(__file__).parent.parent / ".venv" / "bin" / "python"
SCRIPT_PATH = SCRIPTS_DIR / "rule_extraction.py"


# ── Synthetic data fixtures ─────────────────────────────────────────────────

@pytest.fixture
def synthetic_data():
    """Small synthetic dataset for unit tests (no CSV dependency)."""
    rng = np.random.RandomState(42)
    n = 200
    n_features = 10
    feature_names = [f"d_feature_{i}" for i in range(n_features)]

    X = rng.randn(n, n_features)
    # Target: roughly correlated with feature_0 and feature_1
    y = 50 * X[:, 0] + 30 * X[:, 1] + 10 * rng.randn(n)
    groups = np.array([f"game_{i // 20}" for i in range(n)])  # 10 games
    phases = np.array(["opening"] * 60 + ["middlegame"] * 80 + ["endgame"] * 60)

    return X, y, feature_names, groups, phases


@pytest.fixture
def synthetic_discrete(synthetic_data):
    """Synthetic data with discretized target."""
    from rule_extraction import discretize_target
    X, y, feature_names, groups, phases = synthetic_data
    y_disc, label_map = discretize_target(y, scheme="3class", threshold=50)
    return X, y_disc, feature_names, groups, phases, label_map


# ── TestDataLoading ──────────────────────────────────────────────────────────

class TestDataLoading:
    """Loading and preparing feature data."""

    @pytest.mark.skipif(not FEATURES_STM_CSV.exists(), reason="CSV not available")
    def test_load_stm_dataset(self):
        from rule_extraction import load_dataset
        df = load_dataset(mode="stm")
        assert len(df) > 20000
        assert "d_eval_stm" in df.columns
        assert "game_id" in df.columns

    @pytest.mark.skipif(not FEATURES_STM_CSV.exists(), reason="CSV not available")
    def test_prepare_features_returns_correct_types(self):
        from rule_extraction import load_dataset, prepare_features
        df = load_dataset(mode="stm")
        X, y, feature_names, groups = prepare_features(df, mode="stm")
        assert isinstance(X, np.ndarray)
        assert isinstance(y, np.ndarray)
        assert isinstance(feature_names, list)
        assert len(feature_names) == X.shape[1]
        assert len(y) == X.shape[0]

    @pytest.mark.skipif(not FEATURES_STM_CSV.exists(), reason="CSV not available")
    def test_prepare_features_excludes_target_and_leaky_columns(self):
        from rule_extraction import load_dataset, prepare_features
        df = load_dataset(mode="stm")
        X, y, feature_names, groups = prepare_features(df, mode="stm")
        assert "d_eval_stm" not in feature_names
        assert "d_game_phase" not in feature_names
        assert "d_is_check" not in feature_names
        assert "d_side_to_move" not in feature_names

    @pytest.mark.skipif(not FEATURES_STM_CSV.exists(), reason="CSV not available")
    def test_prepare_features_drops_nan_rows(self):
        from rule_extraction import load_dataset, prepare_features
        df = load_dataset(mode="stm")
        X, y, feature_names, groups = prepare_features(df, mode="stm")
        assert not np.any(np.isnan(y))


# ── TestDiscretization ───────────────────────────────────────────────────────

class TestDiscretization:
    """Target discretization into categories."""

    def test_3class_discretization(self):
        from rule_extraction import discretize_target
        y = np.array([-100, -60, -30, 0, 20, 40, 70, 100])
        y_disc, label_map = discretize_target(y, scheme="3class", threshold=50)
        assert len(y_disc) == len(y)
        assert set(y_disc) == {0, 1, 2}
        assert label_map[0] == "decline"
        assert label_map[1] == "neutral"
        assert label_map[2] == "improvement"
        # Check assignments
        assert y_disc[0] == 0   # -100 → decline
        assert y_disc[3] == 1   # 0 → neutral
        assert y_disc[7] == 2   # 100 → improvement

    def test_5class_discretization(self):
        from rule_extraction import discretize_target
        y = np.array([-200, -80, -30, 0, 30, 80, 200])
        y_disc, label_map = discretize_target(y, scheme="5class", threshold=50)
        assert len(label_map) == 5

    def test_discretization_preserves_length(self):
        from rule_extraction import discretize_target
        y = np.random.randn(500) * 100
        y_disc, _ = discretize_target(y)
        assert len(y_disc) == 500

    def test_custom_threshold(self):
        from rule_extraction import discretize_target
        y = np.array([-150, -80, 0, 80, 150])
        y_disc_50, _ = discretize_target(y, threshold=50)
        y_disc_100, _ = discretize_target(y, threshold=100)
        # With threshold=100, fewer extreme values
        assert np.sum(y_disc_100 == 1) >= np.sum(y_disc_50 == 1)


# ── TestCrossValidation ─────────────────────────────────────────────────────

class TestCrossValidation:
    """GroupKFold cross-validation preventing game leakage."""

    def test_cv_returns_expected_keys(self, synthetic_data):
        from rule_extraction import cross_validate_model
        X, y, _, groups, _ = synthetic_data
        result = cross_validate_model(X, y, groups, n_splits=3)
        assert "mean_r2" in result
        assert "std_r2" in result
        assert "per_fold_scores" in result
        assert "n_samples" in result

    def test_cv_all_folds_have_scores(self, synthetic_data):
        from rule_extraction import cross_validate_model
        X, y, _, groups, _ = synthetic_data
        result = cross_validate_model(X, y, groups, n_splits=3)
        assert len(result["per_fold_scores"]) == 3

    def test_cv_with_synthetic_data_reasonable_r2(self, synthetic_data):
        from rule_extraction import cross_validate_model
        X, y, _, groups, _ = synthetic_data
        result = cross_validate_model(X, y, groups, n_splits=3)
        # Synthetic data has clear signal, R² should be positive
        assert result["mean_r2"] > 0.0


# ── TestTreeExtraction ───────────────────────────────────────────────────────

class TestTreeExtraction:
    """Extracting rules from decision trees."""

    def test_extract_rules_returns_list(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules
        X, y_disc, feature_names, _, _, label_map = synthetic_discrete
        tree, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        assert isinstance(rules, list)
        assert len(rules) > 0

    def test_rule_has_required_fields(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules
        X, y_disc, feature_names, _, _, label_map = synthetic_discrete
        _, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        rule = rules[0]
        assert hasattr(rule, "rule_id")
        assert hasattr(rule, "antecedent")
        assert hasattr(rule, "consequent_class")
        assert hasattr(rule, "confidence")
        assert hasattr(rule, "coverage")
        assert hasattr(rule, "support")
        assert hasattr(rule, "lift")

    def test_rule_antecedent_structure(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules
        X, y_disc, feature_names, _, _, label_map = synthetic_discrete
        _, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        for rule in rules:
            for cond in rule.antecedent:
                assert hasattr(cond, "feature")
                assert hasattr(cond, "operator")
                assert hasattr(cond, "threshold")
                assert cond.operator in ("<=", ">")

    def test_coverage_sums_to_approximately_one(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules
        X, y_disc, feature_names, _, _, label_map = synthetic_discrete
        _, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        total_coverage = sum(r.coverage for r in rules)
        assert abs(total_coverage - 1.0) < 0.01

    def test_confidence_between_0_and_1(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules
        X, y_disc, feature_names, _, _, label_map = synthetic_discrete
        _, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        for rule in rules:
            assert 0.0 <= rule.confidence <= 1.0

    def test_max_depth_limits_conditions(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules
        X, y_disc, feature_names, _, _, label_map = synthetic_discrete
        _, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        for rule in rules:
            assert len(rule.antecedent) <= 3

    def test_leaf_count_matches_tree(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules
        X, y_disc, feature_names, _, _, label_map = synthetic_discrete
        tree, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        n_leaves = tree.get_n_leaves()
        assert len(rules) == n_leaves


# ── TestRuleMetrics ──────────────────────────────────────────────────────────

class TestRuleMetrics:
    """Rule quality metric computation."""

    def test_lift_greater_than_zero(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules
        X, y_disc, feature_names, _, _, label_map = synthetic_discrete
        _, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        for rule in rules:
            assert rule.lift > 0.0

    def test_support_is_positive(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules
        X, y_disc, feature_names, _, _, label_map = synthetic_discrete
        _, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        for rule in rules:
            assert rule.support > 0


# ── TestPhaseStability ───────────────────────────────────────────────────────

class TestPhaseStability:
    """Phase stability analysis."""

    def test_stability_dict_has_phase_keys(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules, compute_phase_stability
        X, y_disc, feature_names, _, phases, label_map = synthetic_discrete
        _, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        rules = compute_phase_stability(rules, X, y_disc, phases, label_map)
        for rule in rules:
            assert rule.phase_stability is not None
            assert "opening" in rule.phase_stability
            assert "middlegame" in rule.phase_stability
            assert "endgame" in rule.phase_stability


# ── TestOutputFormatting ─────────────────────────────────────────────────────

class TestOutputFormatting:
    """JSON and markdown output formatting."""

    def test_rules_to_json_roundtrips(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules, RuleSet, rules_to_json
        X, y_disc, feature_names, _, _, label_map = synthetic_discrete
        tree, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        rule_set = RuleSet(
            source="test_tree",
            target="d_eval_stm",
            dataset="synthetic",
            n_rules=len(rules),
            tree_depth=3,
            tree_accuracy=0.75,
            rules=rules,
            cross_validation=None,
        )
        j = rules_to_json(rule_set)
        # Should be JSON-serializable
        json_str = json.dumps(j)
        parsed = json.loads(json_str)
        assert parsed["n_rules"] == len(rules)
        assert len(parsed["rules"]) == len(rules)

    def test_markdown_contains_if_then(self, synthetic_discrete):
        from rule_extraction import train_and_extract_rules, RuleSet, rules_to_markdown
        X, y_disc, feature_names, _, _, label_map = synthetic_discrete
        tree, rules = train_and_extract_rules(X, y_disc, feature_names, label_map, max_depth=3)
        rule_set = RuleSet(
            source="test_tree",
            target="d_eval_stm",
            dataset="synthetic",
            n_rules=len(rules),
            tree_depth=3,
            tree_accuracy=0.75,
            rules=rules,
            cross_validation=None,
        )
        md = rules_to_markdown(rule_set)
        assert "IF" in md
        assert "THEN" in md

    def test_format_condition_readable(self):
        from rule_extraction import Condition, format_condition
        cond = Condition(feature="d_initiative_score_stm", operator=">", threshold=3.5)
        text = format_condition(cond)
        assert "d_initiative_score_stm" in text
        assert ">" in text
        assert "3.5" in text


# ── TestCLI ──────────────────────────────────────────────────────────────────

class TestCLI:
    """CLI subcommand integration tests."""

    @pytest.mark.skipif(not FEATURES_STM_CSV.exists(), reason="CSV not available")
    def test_cross_validate_runs(self, tmp_path):
        result = subprocess.run(
            [str(VENV_PYTHON), str(SCRIPT_PATH), "cross-validate", "--splits", "3"],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "mean_r2" in data

    @pytest.mark.skipif(not FEATURES_STM_CSV.exists(), reason="CSV not available")
    def test_extract_rules_creates_json(self, tmp_path):
        output = tmp_path / "rules.json"
        result = subprocess.run(
            [str(VENV_PYTHON), str(SCRIPT_PATH), "extract-rules",
             "--output", str(output), "--depth", "3", "--no-cv"],
            capture_output=True, text=True, timeout=180,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert output.exists()
        data = json.loads(output.read_text())
        assert "rules" in data

    @pytest.mark.skipif(not FEATURES_STM_CSV.exists(), reason="CSV not available")
    def test_summary_creates_markdown(self, tmp_path):
        rules_json = tmp_path / "rules.json"
        report_md = tmp_path / "report.md"
        # First extract rules (skip CV for speed)
        subprocess.run(
            [str(VENV_PYTHON), str(SCRIPT_PATH), "extract-rules",
             "--output", str(rules_json), "--depth", "3", "--no-cv"],
            capture_output=True, text=True, timeout=180,
        )
        # Then summarize
        result = subprocess.run(
            [str(VENV_PYTHON), str(SCRIPT_PATH), "summary",
             "--input", str(rules_json), "--output", str(report_md)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert report_md.exists()
        content = report_md.read_text()
        assert "IF" in content
