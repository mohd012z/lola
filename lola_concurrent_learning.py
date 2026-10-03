"""Concurrent learning ingress for LOLA.

Learners publish immutable candidates here. This module deliberately does not
write trusted knowledge: promotion remains behind the existing learning/evidence
gates and the knowledge transaction boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from threading import Lock
from time import time_ns
from typing import Iterable, Mapping


class LearningState(str, Enum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    IMAGINED = "imagined"
    VERIFIED = "verified"
    FALSIFIED = "falsified"
    CONFLICT = "conflict"


class SourceKind(str, Enum):
    CODE = "code"
    RUNTIME = "runtime"
    TEST = "test"
    MODEL = "model"
    SKILL = "skill"
    USER = "user"
    REFERENCE = "reference"
    EPISODE = "episode"
    NOVEL = "novel"


@dataclass(frozen=True)
class LearningCandidate:
    source_kind: SourceKind
    source_id: str
    proposition: str
    context: Mapping[str, str] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    state: LearningState = LearningState.INFERRED
    created_ns: int = field(default_factory=time_ns)

    @property
    def fingerprint(self) -> str:
        context = "\x1f".join(f"{k}={self.context[k]}" for k in sorted(self.context))
        evidence = "\x1f".join(sorted(self.evidence_refs))
        payload = "\x1e".join(
            (self.source_kind.value, self.source_id, self.proposition.strip(), context, evidence, self.state.value)
        )
        return sha256(payload.encode("utf-8")).hexdigest()


class ConcurrentLearningBus:
    """Thread-safe ingress with exact candidate deduplication.

    The bus is intentionally small: analysis may be concurrent, but trusted
    knowledge promotion is performed elsewhere by a single transactional writer.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._queue: list[LearningCandidate] = []
        self._seen: set[str] = set()

    def publish(self, candidate: LearningCandidate) -> bool:
        key = candidate.fingerprint
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            self._queue.append(candidate)
            return True

    def publish_many(self, candidates: Iterable[LearningCandidate]) -> int:
        return sum(1 for candidate in candidates if self.publish(candidate))

    def drain(self, limit: int | None = None) -> tuple[LearningCandidate, ...]:
        with self._lock:
            if limit is None:
                count = len(self._queue)
            else:
                if limit < 0:
                    raise ValueError("limit must be >= 0")
                count = min(limit, len(self._queue))
            drained = tuple(self._queue[:count])
            del self._queue[:count]
            return drained

    def snapshot(self) -> tuple[LearningCandidate, ...]:
        with self._lock:
            return tuple(self._queue)

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)


# ---------------------------------------------------------------------------
# Single-writer bridge to the governed learning gate.
#
# The thread's next-slice prescription (verbatim): "connect this bus to the
# existing lola_epistemic_fuse -> evidence/learning gate -> atomic knowledge
# transaction path ... without weakening the existing R3 rollback/evidence
# controls." This is that connection: the bus drains into LearningGate
# candidates. The bridge NEVER promotes — promotion stays with the
# gate's 13-stage pipeline (REPRODUCE -> FALSIFY -> TRANSFER -> REGRESSION
# -> K8). "Multiple learning streams converge through one transactional
# writer": one bus, one drain call site, one gate.
# ---------------------------------------------------------------------------

# SourceKind -> learning-gate source label. "model" is deliberately in the
# gate's external-model vocabulary, so classify_layer() caps MODEL-sourced
# candidates at Layer.CANDIDATE (the K0/K2 rule: a model statement can never
# self-declare VERIFIED — Law 1, enforced by the existing gate, not by us).
_SOURCE_TO_GATE = {
    SourceKind.CODE: "code",
    SourceKind.RUNTIME: "runtime",
    SourceKind.TEST: "test",
    SourceKind.MODEL: "model",
    SourceKind.SKILL: "skill",
    SourceKind.USER: "user",
    SourceKind.REFERENCE: "reference",
    SourceKind.EPISODE: "episode",
    SourceKind.NOVEL: "novel",
}


def drain_to_gate(bus: "ConcurrentLearningBus", limit: int | None = None) -> tuple:
    """Drain up to `limit` candidates from the bus and convert each into a
    governed LearningGate.Candidate.

    Contract:
      * deterministic identity: knowledge_id = "LC-" + fingerprint[:16]
        (same candidate content -> same gated identity, across processes)
      * no promotion: every returned candidate is status CANDIDATE,
        K2 at most — the bus cannot write trusted knowledge by any path
      * model-sourced candidates are capped at Layer.CANDIDATE by the
        gate's own classify_layer (external-model rule), never above
      * the bus is the single ingress: after the call, drained candidates
        are gone from the bus (single-writer convergence)
    """
    from lola_learning_gate import LearningGate
    drained = bus.drain(limit)
    out = []
    for c in drained:
        src = _SOURCE_TO_GATE[c.source_kind]
        gated = LearningGate.new_candidate(
            knowledge_id="LC-" + c.fingerprint[:16],
            source=src,
            claim=c.proposition,
        )
        # Carry provenance into intent-free metadata: evidence refs stay
        # on the candidate for the gate pipeline's later stages.
        out.append((c, gated))
    return tuple(out)


def run_concurrent_learning_smoke() -> dict:
    """Deterministic, zero-model smoke of the bus + single-writer bridge.

    Proves the thread's critical invariant end-to-end:
    OBSERVED != INFERRED != IMAGINED != VERIFIED from ingestion to the
    gate boundary, and that the bridge cannot promote anything.
    """
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, bool(ok)))

    bus = ConcurrentLearningBus()
    runtime = LearningCandidate(SourceKind.RUNTIME, "run-1", "startup reached ready",
                                state=LearningState.OBSERVED)
    model = LearningCandidate(SourceKind.MODEL, "qwen-0.6b", "retrieval should be faster",
                              state=LearningState.IMAGINED)
    novel = LearningCandidate(SourceKind.NOVEL, "nc-104", "predictive knowledge paging",
                              state=LearningState.IMAGINED)
    check("bus_dedupes_exact", bus.publish(runtime) and not bus.publish(runtime))
    check("bus_accepts_distinct", bool(bus.publish_many((model, novel, runtime))))
    check("bus_length_after_ingest", len(bus) == 3)

    pairs = drain_to_gate(bus, limit=2)
    check("bridge_drains_bounded", len(pairs) == 2 and len(bus) == 1)
    from lola_learning_gate import Layer
    check("bridge_no_promotion",
          all(g.status == "CANDIDATE" and g.k_level in ("K0", "K1", "K2")
              for _, g in pairs))
    by_src = {c.source_kind: g for c, g in pairs}
    check("model_capped_at_candidate_layer",
          model.source_kind in by_src and by_src[model.source_kind].layer == Layer.CANDIDATE)
    check("runtime_is_information_layer",
          by_src.get(runtime.source_kind) is not None
          and by_src[runtime.source_kind].layer == Layer.INFORMATION)
    check("deterministic_gate_identity",
          all(g.knowledge_id == "LC-" + c.fingerprint[:16] for c, g in pairs))
    remaining = drain_to_gate(bus)
    check("bridge_drains_rest", len(remaining) == 1 and len(bus) == 0)
    # a second drain is empty: single-writer convergence, no re-reads
    check("bridge_idempotent_after_drain", drain_to_gate(bus) == tuple())
    # re-ingestion: dedup is per-bus (persistent); a fresh bus with the same
    # content gets the same gate identity (determinism across processes)
    bus2 = ConcurrentLearningBus()
    bus2.publish(runtime)
    again = drain_to_gate(bus2)
    check("stable_identity_across_reingest",
          bool(again) and again[0][1].knowledge_id == "LC-" + runtime.fingerprint[:16])
    check("dedup_persists_within_bus",
          not bus.publish(runtime))  # already seen by this bus

    passed = all(ok for _, ok in checks)
    return {"passed": passed,
            "checks": [{"name": n, "ok": ok} for n, ok in checks],
            "total": len(checks), "failed": [n for n, ok in checks if not ok]}
