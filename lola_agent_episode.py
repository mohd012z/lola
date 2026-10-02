"""Deterministic agent-specific episode projection over Lola M0 events."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Tuple

from lola_cognitive_transaction import CognitiveTransaction, build_cognitive_transaction


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
    transactions: Tuple[CognitiveTransaction, ...] = field(default_factory=tuple)


def _ordered(events: Iterable[Mapping[str, Any]], agent_id: str, trace_id: str):
    selected = []
    for event in events:
        if event.get("trace_id") != trace_id:
            continue
        payload = event.get("payload") or {}
        event_agent = str(payload.get("agent_id", ""))
        target = str(payload.get("target_agent_id", ""))
        parent = str(payload.get("parent_agent", ""))
        child = str(payload.get("child_agent", ""))
        if agent_id in {event_agent, target, parent, child}:
            selected.append(event)
    return tuple(
        sorted(
            selected,
            key=lambda event: (str(event.get("timestamp", "")), str(event.get("id", ""))),
        )
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def build_agent_episode(
    events: Iterable[Mapping[str, Any]], agent_id: str, trace_id: str
) -> AgentEpisode:
    ordered = _ordered(events, agent_id, trace_id)
    task_id = next(
        (str(event.get("task_id", "")) for event in ordered if event.get("task_id")),
        "",
    )
    decisions = []
    results = []
    handoffs = []
    failures = []
    recoveries = []
    verification_evidence = []
    decision_payloads: dict[str, Mapping[str, Any]] = {}
    result_payloads: dict[str, Mapping[str, Any]] = {}
    verified = False
    completion_seen = False

    for event in ordered:
        topic = str(event.get("topic", ""))
        payload = event.get("payload") or {}
        payload_agent = str(payload.get("agent_id", ""))

        if topic == "agent.decision" and payload_agent == agent_id:
            decision_id = str(payload.get("decision_id", ""))
            decisions.append(
                DecisionPoint(
                    decision_id,
                    agent_id,
                    str(payload.get("agent_role", "")),
                    tuple(map(str, payload.get("known_evidence_ids") or ())),
                    tuple(map(str, payload.get("active_hypothesis_ids") or ())),
                    tuple(
                        map(
                            str,
                            payload.get("unknowns")
                            or payload.get("unknowns_before")
                            or (),
                        )
                    ),
                    tuple(map(str, payload.get("alternatives") or ())),
                    str(payload.get("selected_action", "")),
                    str(payload.get("selection_basis", "")),
                    payload.get("expected_information_gain"),
                    payload.get("expected_cost"),
                )
            )
            if decision_id and decision_id not in decision_payloads:
                decision_payloads[decision_id] = payload

        elif topic == "agent.decision.result" and payload_agent == agent_id:
            decision_id = str(payload.get("decision_id", ""))
            results.append(
                DecisionResult(
                    decision_id,
                    payload.get("actual_information_gain"),
                    payload.get("actual_cost"),
                    tuple(map(str, payload.get("result_event_ids") or ())),
                    bool(payload.get("revision_triggered", False)),
                )
            )
            if decision_id:
                result_payloads[decision_id] = payload

        elif topic == "agent.handoff" and agent_id in {
            str(payload.get("parent_agent", "")),
            str(payload.get("child_agent", "")),
            payload_agent,
        }:
            handoffs.append(
                Handoff(
                    str(payload.get("handoff_id", "")),
                    str(payload.get("parent_agent", "")),
                    str(payload.get("child_agent", "")),
                    str(payload.get("requested_capability", "")),
                    str(payload.get("objective", "")),
                    tuple(map(str, payload.get("inherited_evidence_ids") or ())),
                    tuple(map(str, payload.get("inherited_assumptions") or ())),
                    tuple(map(str, payload.get("unresolved_unknowns") or ())),
                )
            )

        elif topic == "agent.failure" and payload_agent == agent_id:
            failures.append(event)

        elif topic == "agent.recovery" and payload_agent == agent_id:
            recoveries.append(event)

        elif topic == "agent.complete" and payload_agent == agent_id:
            completion_seen = True

        elif topic == "cognitive.verification" and str(
            payload.get("target_agent_id", "")
        ) == agent_id:
            if payload.get("verified") is True:
                verified = True
                for evidence_id in payload.get("evidence_ids") or ():
                    value = str(evidence_id)
                    if value and value not in verification_evidence:
                        verification_evidence.append(value)

    result_ids = {result.decision_id for result in results if result.decision_id}
    unresolved = tuple(
        decision.decision_id
        for decision in decisions
        if decision.decision_id and decision.decision_id not in result_ids
    )

    transactions = []
    for decision in decisions:
        decision_payload = decision_payloads.get(decision.decision_id)
        result_payload = result_payloads.get(decision.decision_id)
        if not decision_payload or not result_payload:
            continue
        transactions.append(
            build_cognitive_transaction(
                transaction_id=decision.decision_id,
                state_before=_mapping(decision_payload.get("state_before")),
                action=decision.selected_action,
                expected_delta=_mapping(decision_payload.get("expected_delta")),
                state_after=_mapping(result_payload.get("state_after")),
                evidence_ids=result_payload.get("evidence_ids") or (),
            )
        )

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

    return AgentEpisode(
        agent_id=agent_id,
        trace_id=trace_id,
        task_id=task_id,
        events=ordered,
        decisions=tuple(decisions),
        decision_results=tuple(results),
        handoffs=tuple(handoffs),
        failures=tuple(failures),
        recoveries=tuple(recoveries),
        unresolved_decision_ids=unresolved,
        verification_evidence_ids=tuple(verification_evidence),
        outcome=outcome,
        transactions=tuple(transactions),
    )
