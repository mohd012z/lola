"""Deterministic independent corroboration for cognitive evidence."""
from dataclasses import dataclass, field
from typing import Iterable, Tuple

from lola_cognitive_fabric import KIPEnvelope


@dataclass(frozen=True)
class CorroborationResult:
    claim_key: str
    evidence_ids: Tuple[str, ...]
    independent_sources: Tuple[str, ...]
    evidence_grade: str
    conflicts: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def independently_corroborated(self) -> bool:
        return len(self.independent_sources) >= 2 and not self.conflicts


def corroborate(claim_key: str, observations: Iterable[KIPEnvelope]) -> CorroborationResult:
    seen_events, evidence_ids, by_value = set(), [], {}
    for obs in observations:
        if obs.id in seen_events:
            continue
        seen_events.add(obs.id)
        if obs.evidence_id:
            evidence_ids.append(obs.evidence_id)
        value = repr(obs.payload.get("value"))
        by_value.setdefault(value, set()).add(obs.source)
    conflicts = tuple(sorted(by_value)) if len(by_value) > 1 else ()
    sources = tuple(sorted(next(iter(by_value.values()), set()))) if not conflicts else tuple(sorted(set().union(*by_value.values())))
    grade = "E2_CORROBORATED" if len(sources) >= 2 and not conflicts else "E0_DIRECT"
    return CorroborationResult(claim_key, tuple(dict.fromkeys(evidence_ids)), sources, grade, conflicts)
