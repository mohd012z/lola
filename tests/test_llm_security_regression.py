from llm_security.regression import RegressionBudget, compare_metrics


def test_regression_gate_accepts_small_metric_movement():
    baseline = {"false_positive_rate": 0.10, "recall": 0.90, "f1": 0.88}
    candidate = {"false_positive_rate": 0.11, "recall": 0.89, "f1": 0.87}
    result = compare_metrics(baseline, candidate)
    assert result.passed
    assert all(result.checks.values())


def test_regression_gate_rejects_fpr_regression():
    baseline = {"false_positive_rate": 0.10, "recall": 0.90, "f1": 0.88}
    candidate = {"false_positive_rate": 0.14, "recall": 0.90, "f1": 0.88}
    result = compare_metrics(baseline, candidate)
    assert not result.passed
    assert not result.checks["false_positive_rate"]


def test_regression_gate_respects_custom_budget():
    baseline = {"false_positive_rate": 0.10, "recall": 0.90, "f1": 0.88}
    candidate = {"false_positive_rate": 0.13, "recall": 0.86, "f1": 0.85}
    budget = RegressionBudget(max_fpr_increase=0.05, max_recall_drop=0.05, max_f1_drop=0.05)
    assert compare_metrics(baseline, candidate, budget).passed
