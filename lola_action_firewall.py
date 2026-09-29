#!/usr/bin/env python3
"""Capability-based authorization boundary for LOLA actions.

Content can influence risk classification, but it cannot create capabilities.
The caller must supply capabilities from application policy or another trusted
control-plane source.
"""
from __future__ import annotations

from collections.abc import Iterable

from lola_security import (
    ActionClass,
    Decision,
    DecisionEngine,
    ProposedAction,
    SecurityDecision,
    TrustEnvelope,
)
from lola_security_contracts import ActionRequest, Capability, ContractActionClass


_CLASS_MAP = {
    ContractActionClass.READ: ActionClass.READ,
    ContractActionClass.TRANSFORM: ActionClass.TRANSFORM,
    ContractActionClass.MEMORY_WRITE: ActionClass.MEMORY_WRITE,
    ContractActionClass.SIDE_EFFECT: ActionClass.SIDE_EFFECT,
}


class ActionFirewall:
    """Fail-closed capability gate in front of the existing decision engine."""

    def __init__(self, engine: DecisionEngine | None = None) -> None:
        self._engine = engine or DecisionEngine()

    def authorize(
        self,
        request: ActionRequest,
        env: TrustEnvelope,
        granted_capabilities: Iterable[Capability],
    ) -> SecurityDecision:
        granted = frozenset(granted_capabilities)
        missing = request.requested_capabilities - granted

        if missing:
            reasons = tuple(
                sorted(f"MISSING_CAPABILITY:{capability.value}" for capability in missing)
            )
            return SecurityDecision(
                decision=Decision.DENY,
                score=0,
                reasons=reasons,
                source_hash=env.sha256,
                action=request.name,
            )

        # Authorization is derived only from the capability set supplied by the
        # trusted caller. authorization_source is audit metadata, never authority.
        explicitly_authorized = bool(request.requested_capabilities)
        proposed = ProposedAction(
            name=request.name,
            action_class=_CLASS_MAP[request.action_class],
            scope=request.scope,
            explicitly_authorized=explicitly_authorized,
        )
        return self._engine.evaluate(env, proposed)
