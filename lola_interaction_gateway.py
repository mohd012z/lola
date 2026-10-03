"""Interaction Gateway v1 — the human/user control plane on top of the
Lola cognitive fabric (see docs/superpowers/specs/interaction-gateway-v1.md).

Everything between a human and KERNEL_AI: identity + session, input
normalization to KIPEnvelope, and a default-deny routing gate.

The four laws (frozen in the spec):
  Law 1 — user input is evidence, never verification (enforced by
          lola_epistemic_fuse, not here)
  Law 2 — default-deny gate: actor known, trust class bound,
          capability available + exact authority scope
  Law 3 — the sovereign (S0, no-model) path must stay reachable
  Law 4 — denials escalate back to the human on their own transport

The gateway is stateless except the session table. It normalizes and
gates only; it never interprets commands.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from lola_cognitive_fabric import KIPEnvelope
from lola_sovereign_runtime import CapabilityEnvelope, select_capability

TRANSPORTS = frozenset({"cli", "android", "telegram", "web", "api", "handoff"})
_PROVENANCE_KEYS = ("actor_id", "session_id", "transport", "trust_class", "authority")


class TrustClass(str, Enum):
    LOCAL_DEVICE = "LOCAL_DEVICE"
    TOKEN_BOUND = "TOKEN_BOUND"
    UNTRUSTED = "UNTRUSTED"


@dataclass(frozen=True)
class ActorIdentity:
    actor_id: str
    trust_class: TrustClass
    granted_scopes: frozenset = field(default_factory=frozenset)

    def authority(self, scope: str) -> bool:
        """Execution authority is trust-class bound and scope-exact.

        UNTRUSTED actors can never execute, regardless of scopes;
        LOCAL_DEVICE and TOKEN_BOUND may execute only the exact scope
        they were granted.
        """
        if self.trust_class is TrustClass.UNTRUSTED:
            return False
        return str(scope) in set(self.granted_scopes)


class SessionTable:
    """The only state the gateway holds: session records for escalation.

    Session ids are deterministic per (actor, transport, order) so a
    fresh table reopens the same first session — useful for replay and
    for tests.
    """

    def __init__(self) -> None:
        self._counters: dict[tuple[str, str], int] = {}
        self._records: dict[str, dict[str, str]] = {}

    def open_session(self, actor_id: str, transport: str) -> str:
        if str(transport) not in TRANSPORTS:
            raise ValueError(f"unknown transport {transport!r}")
        actor_id = str(actor_id)
        transport = str(transport)
        n = self._counters.get((actor_id, transport), 0)
        self._counters[(actor_id, transport)] = n + 1
        digest = hashlib.sha256(f"{actor_id}|{transport}|{n}".encode()).hexdigest()[:16]
        session_id = f"sess-{digest}"
        self._records[session_id] = {"actor_id": actor_id, "transport": transport}
        return session_id

    def get_session(self, session_id: str, transport: str) -> dict[str, str] | None:
        rec = self._records.get(str(session_id))
        if rec is None or rec["transport"] != str(transport):
            return None
        return dict(rec)


def normalize_user_input(
    transport: str,
    raw: str,
    actor: ActorIdentity,
    *,
    session_id: str,
    kind: str = "query",
    capability: str = "",
    requires_execution: bool = False,
    execution_scope: str | None = None,
) -> KIPEnvelope:
    """Turn one raw human input into a KIPEnvelope with the five-key
    provenance contract. Raises ValueError on any malformed input."""
    if str(transport) not in TRANSPORTS:
        raise ValueError(f"unknown transport {transport!r}")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("input must be a non-empty string")
    if str(kind) not in ("command", "query"):
        raise ValueError(f"kind must be 'command' or 'query', got {kind!r}")
    if requires_execution and not execution_scope:
        raise ValueError("execution commands require an execution_scope")
    if not requires_execution and execution_scope:
        raise ValueError("execution_scope requires requires_execution=True")
    if not str(capability):
        raise ValueError("capability is required")

    authority = f"EXECUTE:{execution_scope}" if requires_execution else "ADVISORY"
    payload: dict[str, Any] = {
        "input": raw.strip(),
        "capability": str(capability),
        "requires_execution": bool(requires_execution),
    }
    if requires_execution:
        payload["execution_scope"] = str(execution_scope)

    provenance = {
        "actor_id": str(actor.actor_id),
        "session_id": str(session_id),
        "transport": str(transport),
        "trust_class": actor.trust_class.value,
        "authority": authority,
    }
    assert set(provenance.keys()) == set(_PROVENANCE_KEYS)

    direct = actor.trust_class is TrustClass.LOCAL_DEVICE
    return KIPEnvelope(
        kind=str(kind),
        topic=f"user.{capability}",
        source=f"{transport}:{actor.actor_id}",
        payload=payload,
        direct=direct,
        reliability=1.0 if direct else 0.8,
        provenance=provenance,
    )


@dataclass(frozen=True)
class RoutedCommand:
    """Gate verdict for one normalized envelope.

    `escalation` is (session_id, transport, reason) — the denial's way
    back to the human on their own channel (Law 4).
    """

    path: str
    execution_authority: bool = False
    capability: str = ""
    denied_reasons: tuple = field(default_factory=tuple)
    escalation: tuple | None = None


def interaction_gate(
    envelope: KIPEnvelope,
    *,
    actors: Mapping[str, ActorIdentity],
    availability: CapabilityEnvelope,
) -> RoutedCommand:
    """Default-deny routing gate (Law 2).

    Check order: actor known -> trust class bound -> capability
    available -> execution authority. Unknown-actor and trust-mismatch
    denials stop immediately (fail-closed, no capability probing).
    """
    prov = dict(envelope.provenance or {})
    actor_id = str(prov.get("actor_id", ""))
    transport = str(prov.get("transport", ""))
    session_id = str(prov.get("session_id", ""))
    capability = str(envelope.payload.get("capability", ""))
    requires_execution = bool(envelope.payload.get("requires_execution", False))
    execution_scope = str(envelope.payload.get("execution_scope", ""))

    def _deny(reason: str) -> RoutedCommand:
        return RoutedCommand(
            path="FAST",
            execution_authority=False,
            capability=capability,
            denied_reasons=(reason,),
            escalation=(session_id, transport, reason),
        )

    actor = actors.get(actor_id)
    if actor is None:
        return _deny("UNKNOWN_ACTOR")
    if prov.get("trust_class") != actor.trust_class.value:
        return _deny("TRUST_MISMATCH")

    if select_capability(availability, local_candidates=(capability,), remote_candidates=(capability,)) is None:
        return _deny("CAPABILITY_UNAVAILABLE")

    if requires_execution and not actor.authority(execution_scope):
        return _deny("AUTHORITY_DENIED")

    path = "COGNITIVE" if requires_execution else "FAST"
    return RoutedCommand(
        path=path,
        execution_authority=requires_execution,
        capability=capability,
    )


# --- LLM source fabric (Law 3) ----------------------------------------------

_TIER_ORDER = ("tiny_local", "large_local", "remote_optional")
_TIER_PLACEMENT = {t: ("local" if t in ("tiny_local", "large_local") else "remote") for t in _TIER_ORDER}
_LLM_GRADE = "E3_INFERRED"


def llm_source_envelope(tiers, *, network_available: bool) -> CapabilityEnvelope:
    """Express the Tiny/Large/Remote source fabric as a CapabilityEnvelope.

    Local tiers are always available; the remote tier only counts when
    `network_available` is True. An empty tier set yields the S0
    sovereign envelope: no models at all, nothing to select.
    """
    local: list[str] = []
    remote: list[str] = []
    tiers_clean = []
    for tier in (str(t) for t in tiers):
        if tier not in _TIER_PLACEMENT:
            raise ValueError(f"unknown LLM tier {tier!r}")
        tiers_clean.append(tier)
    for tier in sorted(tiers_clean, key=_TIER_ORDER.index):
        (local if _TIER_PLACEMENT[tier] == "local" else remote).append(tier)
    return CapabilityEnvelope(local=tuple(local), remote=tuple(remote), network_available=bool(network_available))


def grade_llm_output(source: str) -> str:
    """Evidence grade for any LLM fabric output: capped at E3_INFERRED.

    A model statement can never self-certify as E0–E2.
    """
    if str(source) not in _TIER_PLACEMENT:
        raise ValueError(f"not an LLM fabric tier: {source!r}")
    return _LLM_GRADE
