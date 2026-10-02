"""Deterministic cognitive transactions for State -> Action -> Delta evidence.

This module deliberately contains no model calls.  It records what an action was
expected to change, computes what actually changed, and exposes prediction error
without granting verification authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Tuple


def _canonical(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    return value


def _unknowns(state: Mapping[str, Any]) -> set[str]:
    return {str(item) for item in (state.get("unknowns") or ())}


def _observed_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}

    before_unknowns = _unknowns(before)
    after_unknowns = _unknowns(after)
    removed = tuple(sorted(before_unknowns - after_unknowns))
    added = tuple(sorted(after_unknowns - before_unknowns))
    if removed:
        delta["unknowns_removed"] = removed
    if added:
        delta["unknowns_added"] = added

    if before.get("status") != after.get("status"):
        delta["status_changed_to"] = after.get("status")

    ignored = {"unknowns", "status"}
    changed_fields = tuple(
        sorted(
            str(key)
            for key in (set(before) | set(after)) - ignored
            if _canonical(before.get(key)) != _canonical(after.get(key))
        )
    )
    if changed_fields:
        delta["changed_fields"] = changed_fields

    return delta


def _prediction_error(expected: Mapping[str, Any], observed: Mapping[str, Any]) -> bool:
    """A prediction is satisfied when every predicted delta is observed.

    Observations may contain additional useful changes; those are not prediction
    errors because the expected delta is intentionally allowed to be minimal.
    """
    for key, value in expected.items():
        if key not in observed or _canonical(observed[key]) != _canonical(value):
            return True
    return False


@dataclass(frozen=True)
class CognitiveTransaction:
    transaction_id: str
    state_before: Mapping[str, Any]
    action: str
    expected_delta: Mapping[str, Any]
    state_after: Mapping[str, Any]
    observed_delta: Mapping[str, Any]
    evidence_ids: Tuple[str, ...] = field(default_factory=tuple)
    prediction_error: bool = False
    progress_made: bool = False
    verification_authority: bool = False


def build_cognitive_transaction(
    *,
    transaction_id: str,
    state_before: Mapping[str, Any],
    action: str,
    expected_delta: Mapping[str, Any],
    state_after: Mapping[str, Any],
    evidence_ids=(),
) -> CognitiveTransaction:
    before = dict(state_before)
    after = dict(state_after)
    expected = dict(expected_delta)
    observed = _observed_delta(before, after)
    evidence = tuple(dict.fromkeys(str(item) for item in evidence_ids if str(item)))
    return CognitiveTransaction(
        transaction_id=str(transaction_id),
        state_before=before,
        action=str(action),
        expected_delta=expected,
        state_after=after,
        observed_delta=observed,
        evidence_ids=evidence,
        prediction_error=_prediction_error(expected, observed),
        progress_made=bool(observed),
        verification_authority=False,
    )
