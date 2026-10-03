"""Sovereign local-first cognitive runtime for LOLA.

The runtime is intentionally deterministic.  It coordinates state, gaps,
capability availability, action selection and observed deltas without making
model calls or granting execution authority.  External models/tools may be
registered as capabilities, but the S0 sovereign path never requires them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Tuple

from lola_cognitive_transaction import CognitiveTransaction, build_cognitive_transaction


@dataclass(frozen=True)
class CapabilityEnvelope:
    """Capabilities visible to Kernel_AI at one point in time."""

    local: Tuple[str, ...] = field(default_factory=tuple)
    remote: Tuple[str, ...] = field(default_factory=tuple)
    network_available: bool = False


@dataclass(frozen=True)
class CognitiveState:
    """Small hot-path state; durable intelligence remains outside the kernel."""

    objective: str
    status: str = "ACTIVE"
    unknowns: Tuple[str, ...] = field(default_factory=tuple)
    contradictions: Tuple[str, ...] = field(default_factory=tuple)
    gap_type: str = "NONE"
    verified: bool = False

    def as_mapping(self) -> dict[str, object]:
        return {
            "objective": self.objective,
            "status": self.status,
            "unknowns": self.unknowns,
            "contradictions": self.contradictions,
            "gap_type": self.gap_type,
            "verified": self.verified,
        }


@dataclass(frozen=True)
class NextAction:
    kind: str
    reason: str
    execution_authority: bool = False


@dataclass(frozen=True)
class RuntimeStep:
    transaction: CognitiveTransaction
    resolution: str
    execution_authority: bool = False


def select_capability(
    envelope: CapabilityEnvelope,
    *,
    local_candidates=(),
    remote_candidates=(),
) -> str | None:
    """Select the first requested capability that is actually available.

    Local capability always wins.  Remote capability is considered only when
    connectivity is explicitly available.  Availability never grants action
    authority; it only identifies a provider for the caller to consider.
    """

    local_available = set(envelope.local)
    for candidate in local_candidates:
        value = str(candidate)
        if value in local_available:
            return value

    if envelope.network_available:
        remote_available = set(envelope.remote)
        for candidate in remote_candidates:
            value = str(candidate)
            if value in remote_available:
                return value

    return None


def next_best_action(state: CognitiveState) -> NextAction:
    """Route the current blocking gap to the smallest useful cognitive action."""

    gap = str(state.gap_type or "NONE").upper()
    if state.contradictions or gap == "CONTRADICTION":
        return NextAction("FALSIFY", "contradiction_requires_discriminating_evidence")

    routes = {
        "KNOWLEDGE": ("QUERY_IN_AI", "missing_validated_knowledge"),
        "OBSERVATION": ("OBSERVE", "missing_direct_observation"),
        "PROCEDURE": ("RETRIEVE_SKILL", "missing_applicable_procedure"),
        "CAUSAL": ("EXPERIMENT", "root_cause_requires_intervention_or_probe"),
        "AMBIGUITY": ("DISCRIMINATE", "ambiguity_requires_separating_evidence"),
        "CAPABILITY": ("ESCALATE", "required_capability_not_available_locally"),
        "NO_PROGRESS": ("REFRAME", "stagnation_requires_strategy_change"),
    }
    if gap in routes:
        kind, reason = routes[gap]
        return NextAction(kind, reason)

    if state.verified and not state.unknowns and not state.contradictions:
        return NextAction("COMPLETE", "verified_goal_state")
    if state.unknowns:
        return NextAction("OBSERVE", "unresolved_unknowns")
    return NextAction("VERIFY", "no_blocking_gap_but_resolution_not_verified")


def apply_observation(
    *,
    transaction_id: str,
    state_before: CognitiveState,
    action: str,
    expected_delta: Mapping[str, object],
    state_after: CognitiveState,
    evidence_ids=(),
) -> RuntimeStep:
    """Record a reality observation and derive the next resolution state.

    A model/user claim of success is never sufficient by itself.  Prediction
    mismatch takes precedence over a claimed verified state so false-solved
    transitions are forced back into investigation.
    """

    transaction = build_cognitive_transaction(
        transaction_id=transaction_id,
        state_before=state_before.as_mapping(),
        action=action,
        expected_delta=expected_delta,
        state_after=state_after.as_mapping(),
        evidence_ids=evidence_ids,
    )

    if transaction.prediction_error:
        resolution = "REFOCUS"
    elif state_after.verified and not state_after.unknowns and not state_after.contradictions:
        resolution = "VERIFIED_SOLVED"
    elif transaction.progress_made:
        resolution = "PROGRESSING"
    else:
        resolution = "STALLED"

    return RuntimeStep(transaction=transaction, resolution=resolution)


def run_sovereign_smoke() -> dict[str, object]:
    """Run a deterministic, network-free S0 runtime proof.

    This proves the Kernel/IN_AI control contract can operate without an
    external AI provider.  It does not claim foundation-model intelligence.
    """

    envelope = CapabilityEnvelope(
        local=("in_ai", "local_tools"),
        remote=(),
        network_available=False,
    )
    selected = select_capability(
        envelope,
        local_candidates=("local_tools",),
        remote_candidates=("frontier_reasoner",),
    )

    before = CognitiveState(
        objective="resolve observed dependency gap",
        status="BLOCKED",
        unknowns=("cause",),
        gap_type="OBSERVATION",
    )
    action = next_best_action(before)
    after = CognitiveState(
        objective=before.objective,
        status="READY",
        unknowns=(),
        gap_type="NONE",
        verified=True,
    )
    step = apply_observation(
        transaction_id="sovereign-smoke-1",
        state_before=before,
        action="inspect dependency",
        expected_delta={"unknowns_removed": ("cause",)},
        state_after=after,
        evidence_ids=("local-observation-1",),
    )

    passed = bool(
        selected == "local_tools"
        and action.kind == "OBSERVE"
        and step.resolution == "VERIFIED_SOLVED"
        and not step.transaction.prediction_error
        and not step.transaction.verification_authority
    )
    return {
        "passed": passed,
        "mode": "S0-SOVEREIGN",
        "external_used": False,
        "selected_capability": selected,
        "action": action.kind,
        "resolution": step.resolution,
        "prediction_error": step.transaction.prediction_error,
        "evidence_ids": list(step.transaction.evidence_ids),
    }
