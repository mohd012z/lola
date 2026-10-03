"""Learning Gate — pre-learning pipeline and K0-K8 knowledge maturity.

docs/superpowers/specs/new-lola-discovery-learning.md, Module C.

"LOLA should not begin *learning* when an external source gives it
information." This module separates five NON-EQUIVALENT layers
(DATA / INFORMATION / CANDIDATE / VERIFIED / LEARNED) and walks every
candidate through a deterministic pre-learning pipeline that stops at the
first failing gate. A candidate is promoted (K8, ACTIVE) only if it
survives REPRODUCE + FALSIFY + TRANSFER + REGRESSION. Learning is not
irreversible: demote() moves knowledge backward on new contradiction.

The K-levels are an *evidence maturity* dimension that complements the
existing lola_knowledge_lifecycle version/state (operational status) — it
does not replace it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class Layer(str, Enum):
    DATA = "DATA"
    INFORMATION = "INFORMATION"
    CANDIDATE = "CANDIDATE"
    VERIFIED = "VERIFIED"
    LEARNED = "LEARNED"


K_LEVELS = ("K0", "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8")
# K0 RAW, K1 OBSERVED, K2 HYPOTHESIS, K3 CORROBORATED, K4 REPRODUCED,
# K5 FALSIFICATION-SURVIVED, K6 TRANSFER-VALIDATED, K7 REGRESSION-CLEARED,
# K8 GOVERNED.

# stage -> K level reached when that stage passes.
_STAGE_TO_K = {
    "REPRODUCE": "K4",
    "FALSIFY": "K5",
    "TRANSFER": "K6",
    "REGRESSION": "K7",
}
_PROMOTE_K = "K8"


def classify_layer(source: str, *, is_external_model: bool) -> Layer:
    """Evidence layer for a source. External AI output caps at CANDIDATE
    (the K0/K2 rule): a model statement can never self-declare VERIFIED or
    LEARNED. Internal direct observation starts at INFORMATION; only the
    epistemic fuse (observation-grade evidence) can raise a claim to
    VERIFIED, and LEARNED is granted solely by governed promotion."""
    if not str(source).strip():
        raise ValueError("source is required")
    if is_external_model:
        return Layer.CANDIDATE
    return Layer.INFORMATION


@dataclass
class Candidate:
    knowledge_id: str
    source: str
    claim: str
    layer: Layer
    k_level: str = "K2"
    status: str = "CANDIDATE"  # CANDIDATE | ACTIVE | QUARANTINED | REJECTED
    intent: dict[str, Any] | None = None
    stages_passed: list[str] = field(default_factory=list)
    quarantine_reason: str | None = None
    reject_reason: str | None = None

    # -- discipline: prediction BEFORE research -----------------------------

    def record_intent(self, *, known=(), unknown=(), prediction: str, counter_prediction: str) -> None:
        """Self-inventory + prediction recorded before any external query.

        Goal-directed learning: the candidate must state what it already
        knows, what gap it closes, and what it expects — otherwise
        research_external is refused (LOLA would merely absorb answers).
        """
        if self.status == "REJECTED":
            raise ValueError("rejected candidates cannot record intent")
        if not str(prediction).strip():
            raise ValueError("prediction is required before external research")
        self.intent = {
            "known": [str(k) for k in known],
            "unknown": [str(u) for u in unknown],
            "prediction": str(prediction),
            "counter_prediction": str(counter_prediction),
        }

    def research_external(self, *, query: str) -> None:
        if not str(query).strip():
            raise ValueError("query is required")
        if self.intent is None:
            raise ValueError("record_intent (self-inventory + prediction) is required before external research")

    # -- 13-stage pipeline (deterministic; stops at first failing gate) ----

    def advance(self, *, reproduce: bool, falsify: bool, transfer: bool, regression: bool) -> str:
        """Walk REPRODUCE → FALSIFY → TRANSFER → REGRESSION → PROMOTE.

        Returns PROMOTED only if all four gates pass and the candidate is
        not quarantined/rejected; otherwise HOLD (not yet rejected), and
        k_level reflects the last stage survived.
        """
        if self.status == "REJECTED":
            return "HOLD"
        for stage, passed in (("REPRODUCE", reproduce), ("FALSIFY", falsify),
                              ("TRANSFER", transfer), ("REGRESSION", regression)):
            if not passed:
                if stage == "REPRODUCE":
                    self.k_level = K_LEVELS[K_LEVELS.index(self.k_level) if self.k_level in K_LEVELS else 2]
                return "HOLD"
            self.stages_passed.append(stage)
            self.k_level = _STAGE_TO_K[stage]

        if self.status == "QUARANTINED":
            return "HOLD"

        self.k_level = _PROMOTE_K
        self.status = "ACTIVE"
        return "PROMOTED"

    # -- lifecycle transitions ---------------------------------------------

    def quarantine(self, *, reason: str) -> None:
        if not str(reason).strip():
            raise ValueError("quarantine reason is required")
        if self.status == "REJECTED":
            raise ValueError("already rejected")
        self.status = "QUARANTINED"
        self.quarantine_reason = str(reason)

    def reject(self, *, reason: str) -> None:
        if not str(reason).strip():
            raise ValueError("reject reason is required")
        self.status = "REJECTED"
        self.reject_reason = str(reason)


class LearningGate:
    """Factory + policy home for pre-learning candidates."""

    @staticmethod
    def new_candidate(*, knowledge_id: str, source: str, claim: str) -> Candidate:
        if not str(knowledge_id).strip() or not str(claim).strip():
            raise ValueError("knowledge_id and claim are required")
        is_external = str(source).lower() in ("claude", "gpt", "qwen", "gemini", "llm", "model", "remote")
        return Candidate(
            knowledge_id=str(knowledge_id),
            source=str(source),
            claim=str(claim),
            layer=classify_layer(source, is_external_model=is_external),
        )


def demote(candidate: Candidate, *, contradiction: str) -> None:
    """Knowledge moves backward: new contradiction lowers the K-level and
    routes the candidate to QUARANTINED for retest. Promotion is not
    irreversible."""
    if not str(contradiction).strip():
        raise ValueError("contradiction is required")
    if candidate.status == "REJECTED":
        raise ValueError("already rejected")
    idx = K_LEVELS.index(candidate.k_level) if candidate.k_level in K_LEVELS else 0
    candidate.k_level = K_LEVELS[max(idx - 2, 0)]  # one full stage back at minimum
    candidate.status = "QUARANTINED"
    candidate.quarantine_reason = f"new contradiction: {contradiction}"
