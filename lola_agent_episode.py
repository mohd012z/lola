"""Deterministic agent-specific episode projection over Lola M0 events."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Tuple


@dataclass(frozen=True)
class DecisionPoint:
    decision_id: str
    agent_id: str
    agent_role: str
    known_evidence_ids: Tuple[str, ...] = field(default_factory=tuple)
    active_hypothesis_ids: Tuple[str, ...] = field(default_factory=tuple)
    unknowns_before: Tuple[str, ...] = field(default_factory=tuple)
    alternatives: Tuple[str, ...] = field(default_factory=tuple)
    selected_action: str = ""
    selection_basis: str = ""
    expected_information_gain: Any = None
    expected_cost: Any = None


@dataclass(frozen=True)
class DecisionResult:
    decision_id: str
    actual_information_gain: Any = None
    actual_cost: Any = None
    result_event_ids: Tuple[str, ...] = field(default_factory=tuple)
    revision_triggered: bool = False


@dataclass(frozen=True)
class Handoff:
    handoff_id: str
    parent_agent: str
    child_agent: str
    requested_capability: str = ""
    objective: str = ""
    inherited_evidence_ids: Tuple[str, ...] = field(default_factory=tuple)
    inherited_assumptions: Tuple[str, ...] = field(default_factory=tuple)
    unresolved_unknowns: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AgentEpisode:
    agent_id: str
    trace_id: str
    task_id: str
    events: Tuple[Mapping[str, Any], ...]
    decisions: Tuple[DecisionPoint, ...]
    decision_results: Tuple[DecisionResult, ...]
    handoffs: Tuple[Handoff, ...]
    failures: Tuple[Mapping[str, Any], ...]
    recoveries: Tuple[Mapping[str, Any], ...]
    unresolved_decision_ids: Tuple[str, ...]
    verification_evidence_ids: Tuple[str, ...]
    outcome: str


def _ordered(events: Iterable[Mapping[str, Any]], agent_id: str, trace_id: str):
    selected = []
    for event in events:
        if event.get("trace_id") != trace_id:
            continue
        payload = event.get("payload") or {}
        event_agent = str(payload.get("agent_id", ""))
        target_agent = str(payload.get("target_agent_id", ""))
        if event_agent == agent_id or target_agent == agent_id:
            selected.append(event)
    return tuple(sorted(selected, key=lambda e: (str(e.get("timestamp", "")), str(e.get("id", "")))))


def build_agent_episode(events: Iterable[Mapping[str, Any]], agent_id: str, trace_id: str) -> AgentEpisode:
    ordered = _ordered(events, agent_id, trace_id)
    task_id = next((str(e.get("task_id", "")) for e in ordered if e.get("task_id")), "")
    decisions = []
    results = []
    handoffs = []
    failures = []
    recoveries = []
    verification_evidence = []
    verified = False
    completion_seen = False

    for event in ordered:
        topic = str(event.get("topic", ""))
        p = event.get("payload") or {}
        if topic == "agent.decision":
            decisions.append(DecisionPoint(
                decision_id=str(p.get("decision_id", "")), agent_id=agent_id,
                agent_role=str(p.get("agent_role", "")),
                known_evidence_ids=tuple(map(str, p.get("known_evidence_ids") or ())),
                active_hypothesis_ids=tuple(map(str, p.get("active_hypothesis_ids") or ())),
                unknowns_before=tuple(map(str, p.get("unknowns") or p.get("unknowns_before") or ())),
                alternatives=tuple(map(str, p.get("alternatives") or ())),
                selected_action=str(p.get("selected_action", "")),
                selection_basis=str(p.get("selection_basis", "")),
                expected_information_gain=p.get("expected_information_gain"), expected_cost=p.get("expected_cost")))
        elif topic == "agent.decision.result":
            results.append(DecisionResult(str(p.get("decision_id", "")), p.get("actual_information_gain"), p.get("actual_cost"), tuple(map(str, p.get("result_event_ids") or ())), bool(p.get("revision_triggered", False))))
        elif topic == "agent.handoff":
            handoffs.append(Handoff(str(p.get("handoff_id", "")), str(p.get("parent_agent", "")), str(p.get("child_agent", "")), str(p.get("requested_capability", "")), str(p.get("objective", "")), tuple(map(str, p.get("inherited_evidence_ids") or ())), tuple(map(str, p.get("inherited_assumptions") or ())), tuple(map(str, p.get("unresolved_unknowns") or ()))))
        elif topic == "agent.failure":
            failures.append(event)
        elif topic == "agent.recovery":
            recoveries.append(event)
        elif topic == "agent.complete":
            completion_seen = True
        elif topic == "cognitive.verification" and str(p.get("target_agent_id", "")) == agent_id:
            if p.get("verified") is True:
                verified = True
                for eid in p.get("evidence_ids") or ():
                    sid = str(eid)
                    if sid and sid not in verification_evidence:
                        verification_evidence.append(sid)

    result_ids = {r.decision_id for r in results if r.decision_id}
    unresolved = tuple(d.decision_id for d in decisions if d.decision_id and d.decision_id not in result_ids)
    if verified and completion_seen and not unresolved:
        outcome = "VERIFIED"
    elif unresolved:
        outcome = "PARTIAL"
    elif failures and not recoveries:
        outcome = "FAILED"
    elif completion_seen or recoveries or decisions:
        outcome = "INCONCLUSIVE"
    else:
        outcome = "PARTIAL"

    return AgentEpisode(agent_id, trace_id, task_id, ordered, tuple(decisions), tuple(results), tuple(handoffs), tuple(failures), tuple(recoveries), unresolved, tuple(verification_evidence), outcome)
