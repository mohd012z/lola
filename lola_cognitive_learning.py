"""Governed consolidation for verified Lola cognitive episodes."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple
from lola_cognitive_episode import Episode

@dataclass(frozen=True)
class LessonCandidate:
    trace_id: str
    task_id: str
    evidence_ids: Tuple[str, ...]
    prediction_accuracy: float
    applicability: Tuple[str, ...]
    conflicts: Tuple[str, ...]
    reversible: bool = True
    status: str = "CANDIDATE"

def candidate_from_episode(episode: Episode) -> LessonCandidate | None:
    """Create a reversible candidate only; never mutate permanent memory here."""
    if episode.outcome != "VERIFIED" or not episode.supporting_evidence_ids:
        return None
    total=len(episode.prediction_deltas)
    accuracy=(sum(1 for d in episode.prediction_deltas if d.matched)/total) if total else 1.0
    applicability=tuple(sorted({k for d in episode.prediction_deltas for k in d.expected.keys()}))
    conflicts=tuple(episode.verification_failures)
    if conflicts:
        return None
    return LessonCandidate(episode.trace_id,episode.task_id,episode.supporting_evidence_ids,accuracy,applicability,conflicts)
