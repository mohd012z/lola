"""Recheck feedback edge — PREDICTION ERROR -> ROOT CAUSE / NEW GAP.

docs/superpowers/specs/loop-runner-and-recheck-v1.md, Module P.

Closes the master flow's feedback edge: when the observed outcome deviates
from the prediction beyond tolerance, the loop does NOT answer — it names
the root-cause gap and continues into OBSERVE/TEST. Each attempt is one
cycle; the next expected/observed pair supplied by the caller IS the
recheck attempt. Deterministic, bounded, never invents observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class RecheckResult:
    cycles: tuple              # tuple[dict] — per-cycle records
    needs_recheck: bool        # any cycle exceeded tolerance
    prediction_error: float    # final cycle's signed delta
    root_cause_gap: str | None # named when the loop must re-check
    continued: bool            # True = loop may answer; False = stop first


def recheck_cycle(
    expected_values: Sequence[float],
    observed_values: Sequence[float],
    *,
    tolerance: float = 1.0,
    max_cycles: int = 3,
) -> RecheckResult:
    if len(expected_values) != len(observed_values):
        raise ValueError(
            "expected/observed value counts must match "
            f"({len(expected_values)} vs {len(observed_values)})"
        )
    n = min(len(expected_values), max_cycles)
    cycles = []
    for i in range(n):
        expected = float(expected_values[i])
        observed = float(observed_values[i])
        delta = observed - expected
        bad = abs(delta) > tolerance
        cycles.append({
            "cycle": i,
            "expected": expected,
            "observed": observed,
            "delta": delta,
            "needs_recheck": bad,
        })
        if bad:
            return RecheckResult(
                cycles=tuple(cycles),
                needs_recheck=True,
                prediction_error=delta,
                root_cause_gap=f"prediction error at cycle {i} (delta {delta:+g})",
                continued=False,
            )
    return RecheckResult(
        cycles=tuple(cycles),
        needs_recheck=False,
        prediction_error=cycles[-1]["delta"],
        root_cause_gap=None,
        continued=True,
    )
