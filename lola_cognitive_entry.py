"""Cognitive Entry — gateway -> KIPEnvelope -> loop, one call.

docs/superpowers/specs/cognitive-entry-v1.md, Module R.

The connective tissue between the Interaction Gateway (#43) and the
cognitive loop (#46-#49). HUMAN -> transports -> GATEWAY -> KIPEnvelope
-> KERNEL -> loop -> answer is now a single deterministic call, and the
default-deny gate (Law 2) is exercised BEFORE any cognition happens.

Stages (frozen):
  1. NORMALIZE  raw input -> KIPEnvelope (5-key provenance)
  2. GATE       interaction_gate: DENIED -> no cognition, escalate (Law 4);
                ALLOWED -> continue
  3. RUN        run_cognitive_loop on the envelope's question
  4. FUSE       Law 1: external/verified claims are graded by the
                epistemic fuse — a user claim is never verification

EntryResult is flat and JSON-safe: the report carries the LoopReport
fields directly (route, confidence, evidence_ids, ...), with the
runner's roles / flow / governor / recheck as top-level siblings.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from lola_cognitive_loop import run_cognitive_loop
from lola_epistemic_fuse import epistemic_fuse
from lola_interaction_gateway import (
    ActorIdentity,
    CapabilityEnvelope,
    interaction_gate,
    normalize_user_input,
)


@dataclass(frozen=True)
class EntryResult:
    status: str                 # DENIED | ANSWERED
    gate: dict                  # asdict(RoutedCommand)
    report: dict | None         # LoopReport fields (None when denied)
    roles: list | None          # derived cognitive roles
    flow: str | None            # /flow operational trace
    governor: str | None        # learning governor verdict
    recheck: dict | None        # named prediction-error feedback edge
    fuse: dict | None           # epistemic fuse verdict (None if no external evidence)
    escalation: tuple | None    # (session_id, transport, reason) on denial
    session_id: str
    transport: str


def _default_s0(capability: str) -> CapabilityEnvelope:
    # The sovereign no-model path (Law 3) stays reachable: the capability
    # is available locally, nothing remote, so only trust/actor/scope
    # checks can deny.
    return CapabilityEnvelope(local=(capability,), remote=(),
                              network_available=False)


def cognitive_entry(
    transport: str,
    raw: str,
    actor: ActorIdentity,
    *,
    session_id: str,
    actors: Mapping[str, ActorIdentity],
    availability: CapabilityEnvelope | None = None,
    capability: str = "cognitive_query",
    requires_execution: bool = False,
    execution_scope: str | None = None,
    verified_state: Mapping[str, str] | None = None,
    inspectable: Sequence[str] = (),
    inventory: Mapping[str, Sequence[str]] | None = None,
    frozen_idea: Mapping[str, Any] | None = None,
    external_hits: Sequence[str] = (),
    prediction: float | None = None,
    observed: float | None = None,
) -> EntryResult:
    availability = availability if availability is not None else _default_s0(capability)

    # 1. NORMALIZE
    envelope = normalize_user_input(
        transport, raw, actor,
        session_id=session_id,
        kind="command" if requires_execution else "query",
        capability=capability,
        requires_execution=requires_execution,
        execution_scope=execution_scope,
    )

    # 2. GATE (default-deny BEFORE any cognition)
    gate = interaction_gate(envelope, actors=actors, availability=availability)
    if gate.denied_reasons:
        return EntryResult(
            status="DENIED", gate=dataclasses.asdict(gate),
            report=None, roles=None, flow=None, governor=None,
            recheck=None, fuse=None, escalation=gate.escalation,
            session_id=session_id, transport=transport,
        )

    # 3. RUN — the envelope's input is the question
    loop_input = {
        "question": envelope.payload["input"],
        "verified_state": verified_state or {},
        "inspectable": tuple(inspectable),
        "inventory": inventory,
        "frozen_idea": frozen_idea,
        "external_hits": tuple(external_hits),
        "prediction": prediction,
        "observed": observed,
    }
    runner = run_cognitive_loop(loop_input, task_id="entry")
    report = runner["report"]

    # 4. FUSE (Law 1) — only when external evidence is involved
    fuse = None
    if external_hits:
        confidence = report["confidence"]
        ev_ids = report["evidence_ids"]
        quarantined = bool(report["quarantined"])
        # observation-grade evidence = the bus's external:* ids that are
        # actually cited. A quarantined run carries them as contradictions
        # (never as support), so nothing is "observed" -> CUT.
        observed_ids = [] if quarantined else list(ev_ids)
        verdict = epistemic_fuse(
            verified=(confidence == "SUPPORTED"),
            evidence_ids=ev_ids,
            observation_evidence_ids=observed_ids,
            contradictions=(["quarantined"] if quarantined else []),
        )
        fuse = {"result": verdict.result, "reason": verdict.reason}

    return EntryResult(
        status="ANSWERED", gate=dataclasses.asdict(gate),
        report=report, roles=runner["roles"], flow=runner["flow"],
        governor=runner["governor"], recheck=runner.get("recheck"),
        fuse=fuse, escalation=None, session_id=session_id,
        transport=transport,
    )
