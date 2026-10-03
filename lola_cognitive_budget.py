"""Cognitive budget + runtime stop conditions.

docs/superpowers/specs/new-lola-cognitive-mesh-controls.md, Module F.

Deep research can loop forever; a small local system needs explicit
exit ramps. Every question carries a budget across several axes, and
the run stops at the FIRST condition that fires, checked in a fixed
order. "Answered with sufficient evidence" always beats "budget
reached" — a finished job is not penalized for being finished.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

AXES = ("depth", "agents", "tokens", "tool_calls", "research",
        "external_access", "latency_ms")

_INFO_GAIN_FLOOR = 0.1   # below this the next step barely moves the answer


@dataclass
class CognitiveBudget:
    depth: int = 4
    agents: int = 8
    tokens: int = 20000
    tool_calls: int = 50
    research: int = 4
    external_access: int = 2
    latency_ms: int = 300000

    def __post_init__(self) -> None:
        for axis, limit in self.as_limits().items():
            if limit < 0:
                raise ValueError(f"budget {axis} must be >= 0")
        self.used: dict = {axis: 0 for axis in self.as_limits()}

    def as_limits(self) -> dict:
        return {axis: getattr(self, axis) for axis in AXES}

    def consume(self, axis: str, amount: int = 1) -> None:
        if axis not in self.used:
            raise KeyError(axis)
        self.used[axis] += amount

    def exhausted(self, axis: str) -> bool:
        if axis not in self.used:
            raise KeyError(axis)
        return self.used[axis] >= self.as_limits()[axis]

    def any_exhausted(self) -> bool:
        return any(self.exhausted(a) for a in AXES)


# Stop conditions in check order. A run continues while none fire.
STOP_ANSWERED = "ANSWERED_WITH_EVIDENCE"
STOP_NO_DECISION_CHANGE = "UNCERTAINTY_CHANGES_NOTHING"
STOP_LOW_GAIN = "LOW_INFORMATION_GAIN"
STOP_BUDGET = "BUDGET_REACHED"
STOP_NO_EVIDENCE = "EVIDENCE_UNAVAILABLE"
STOP_HUMAN = "HUMAN_DECISION_REQUIRED"


def stop_condition(state: Mapping[str, Any]) -> str | None:
    """Return the first stop condition that fires, else None (continue).

    state keys:
      answered: bool              (answered WITH sufficient evidence)
      uncertainty_changes_decision: bool
      info_gain: float            (estimated value of the next step)
      budget: CognitiveBudget
      evidence_available: bool
      human_required: bool
    """
    if state.get("answered"):
        return STOP_ANSWERED
    if not state.get("uncertainty_changes_decision", True):
        return STOP_NO_DECISION_CHANGE
    if float(state.get("info_gain", 1.0)) < _INFO_GAIN_FLOOR:
        return STOP_LOW_GAIN
    budget = state.get("budget")
    if budget is not None and budget.any_exhausted():
        return STOP_BUDGET
    if not state.get("evidence_available", True):
        return STOP_NO_EVIDENCE
    if state.get("human_required"):
        return STOP_HUMAN
    return None
