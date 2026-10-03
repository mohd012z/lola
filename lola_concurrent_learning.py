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
