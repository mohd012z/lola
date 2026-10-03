"""Observe stage — TEST → OBSERVE → PREDICTION ERROR.

docs/superpowers/specs/agent-roles-and-observe-v1.md, Module O.

The master flow's prediction-error loop: before answering, run the test,
observe the outcome, and compute the signed delta (observed - expected).
A drift within tolerance is fine — the answer stands. A delta beyond
tolerance forces a RECHECK (re-observe) before answering.

Self-contained: computes the delta. (Wiring #42's DeltaMemory per-step
store is a post-merge follow-up; the concept matches by construction —
both store the signed prediction error.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def predict(value: Any) -> Any:
    """Identity prediction hook (the "expected" side)."""
    return value


def compute_prediction_error(expected: float, observed: float) -> float:
    """Signed delta: observed - expected. Zero when exact."""
    return observed - expected


@dataclass(frozen=True)
class Observation:
    observation_id: str
    expected: float
    observed: float
    prediction_error: float
    source: str
    needs_recheck: bool


def record_observation(
    observation_id: str,
    *,
    expected: float,
    observed: float,
    source: str = "",
    tolerance: float = 1.0,
) -> Observation:
    err = compute_prediction_error(expected, observed)
    return Observation(
        observation_id=observation_id,
        expected=expected,
        observed=observed,
        prediction_error=err,
        source=source,
        needs_recheck=abs(err) > tolerance,
    )
