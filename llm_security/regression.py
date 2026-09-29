"""Regression gates for Lola's defensive guardrail pipeline.

The gate compares candidate metrics with a stored/approved baseline.  It is
intentionally policy-neutral: callers choose budgets and this module reports
which invariants pass or fail.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping


@dataclass(frozen=True)
class RegressionBudget:
    max_fpr_increase: float = 0.02
    max_recall_drop: float = 0.02
    max_f1_drop: float = 0.02


@dataclass(frozen=True)
class RegressionResult:
    passed: bool
    checks: dict[str, bool]
    deltas: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _metric(metrics: Mapping[str, Any], name: str) -> float:
    value = metrics.get(name, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def compare_metrics(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    budget: RegressionBudget | None = None,
) -> RegressionResult:
    budget = budget or RegressionBudget()

    deltas = {
        "false_positive_rate": round(
            _metric(candidate, "false_positive_rate") - _metric(baseline, "false_positive_rate"), 6
        ),
        "recall": round(_metric(candidate, "recall") - _metric(baseline, "recall"), 6),
        "f1": round(_metric(candidate, "f1") - _metric(baseline, "f1"), 6),
    }

    checks = {
        "false_positive_rate": deltas["false_positive_rate"] <= budget.max_fpr_increase,
        "recall": deltas["recall"] >= -budget.max_recall_drop,
        "f1": deltas["f1"] >= -budget.max_f1_drop,
    }
    return RegressionResult(all(checks.values()), checks, deltas)
