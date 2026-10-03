"""Trace-replay episode engine for Lola's cognitive fabric.

Episodes are deterministic reconstructions of durable cognitive events.  The
engine does not infer missing outcomes: absence remains PARTIAL/UNKNOWN.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Tuple


@dataclass(frozen=True)
class PredictionDelta:
    hypothesis_id: str
    expected: Mapping[str, Any]
    actual: Mapping[str, Any]
    matched: bool
    differences: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class Episode:
    trace_id: str
    task_id: str
    events: Tuple[Mapping[str, Any], ...]
    prediction_deltas: Tuple[PredictionDelta, ...]
    unresolved_predictions: Tuple[str, ...]
    supporting_evidence_ids: Tuple[str, ...]
    outcome: str
    verification_failures: Tuple[str, ...] = field(default_factory=tuple)


def compare_prediction(expected: Mapping[str, Any], actual: Mapping[str, Any], hypothesis_id: str = "") -> PredictionDelta:
    differences = {}
    for key in sorted(set(expected) | set(actual)):
        wanted = expected.get(key, "<MISSING>")
        observed = actual.get(key, "<MISSING>")
        if wanted != observed:
            differences[key] = {"expected": wanted, "actual": observed}
    return PredictionDelta(hypothesis_id, dict(expected), dict(actual), not differences, differences)


def _ordered_trace_events(events: Iterable[Mapping[str, Any]], trace_id: str):
    selected = [e for e in events if e.get("trace_id") == trace_id]
    return tuple(sorted(selected, key=lambda e: (str(e.get("timestamp", "")), str(e.get("id", "")))))


def build_episode(events: Iterable[Mapping[str, Any]], trace_id: str) -> Episode:
    ordered = _ordered_trace_events(events, trace_id)
    task_id = next((str(e.get("task_id", "")) for e in ordered if e.get("task_id")), "")
    predictions = {}
    actuals = {}
    evidence_ids = []
    verified = False
    verification_seen = False
    failures = []

    for event in ordered:
        topic = event.get("topic")
        payload = event.get("payload") or {}
        hid = str(payload.get("hypothesis_id", ""))
        if topic == "cognitive.prediction" and hid:
            predictions[hid] = dict(payload.get("expected") or {})
        elif topic == "cognitive.actual" and hid:
            actuals[hid] = dict(payload.get("actual") or {})
        elif topic == "cognitive.verification":
            verification_seen = True
            if payload.get("verified") is True:
                verified = True
                for evidence_id in payload.get("evidence_ids") or []:
                    if evidence_id and evidence_id not in evidence_ids:
                        evidence_ids.append(str(evidence_id))
            else:
                failures.append(str(payload.get("reason") or "verification_failed"))

    deltas = tuple(compare_prediction(expected, actuals[hid], hid) for hid, expected in predictions.items() if hid in actuals)
    unresolved = tuple(sorted(hid for hid in predictions if hid not in actuals))

    if verified and not unresolved and all(delta.matched for delta in deltas):
        outcome = "VERIFIED"
    elif verification_seen and not verified:
        outcome = "FAILED"
    elif unresolved or not verification_seen:
        outcome = "PARTIAL"
    else:
        outcome = "FAILED"

    return Episode(trace_id, task_id, ordered, deltas, unresolved, tuple(evidence_ids), outcome, tuple(failures))
