"""Epistemic fuse — Law 1 of the interaction gateway spec, made mechanical.

docs/superpowers/specs/interaction-gateway-v1.md: "A human saying 'it
worked' enters as a command/query envelope. Only VERIFY backed by
observation-grade evidence may set verified=True."

The fuse is the last gate before a verified state is accepted into the
world state. It never inspects *what* was claimed — only whether the
claim is bound to observation-grade evidence that actually cites it.

Verdicts:
  PASS / OBSERVED          verified claim cites at least one observation-grade id
  PASS / NOT_VERIFIED      not a verified claim — passes through untouched
  CUT  / CONTRADICTION     unresolved contradiction — always cuts
  CUT  / NO_EVIDENCE       verified with nothing cited
  CUT  / USER_CLAIM_ONLY   cited evidence exists but none is observation-grade
  CUT  / UNBOUND_EVIDENCE  an observation id was asserted but is not among the
                           cited evidence ids (the citation chain is broken)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class FuseVerdict:
    result: str  # PASS | CUT
    reason: str


def epistemic_fuse(
    *,
    verified: bool,
    evidence_ids: Iterable[str],
    observation_evidence_ids: Iterable[str],
    contradictions: Iterable[str] = (),
) -> FuseVerdict:
    cited = {str(e) for e in evidence_ids}
    observed = {str(e) for e in observation_evidence_ids}
    contradiction = sorted({str(c) for c in contradictions if str(c)})

    if contradiction:
        return FuseVerdict("CUT", "CONTRADICTION")

    if not verified:
        return FuseVerdict("PASS", "NOT_VERIFIED")

    if not cited:
        return FuseVerdict("CUT", "NO_EVIDENCE")

    if cited & observed:
        return FuseVerdict("PASS", "OBSERVED")
    if not observed:
        return FuseVerdict("CUT", "USER_CLAIM_ONLY")
    return FuseVerdict("CUT", "UNBOUND_EVIDENCE")
