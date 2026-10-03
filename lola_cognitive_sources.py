"""Internal-source normalization for Lola's cognitive fabric."""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from lola_cognitive_fabric import KIPEnvelope


class EvidenceGrade(str, Enum):
    E0_DIRECT = "E0_DIRECT"
    E1_DERIVED = "E1_DERIVED"
    E2_CORROBORATED = "E2_CORROBORATED"
    E3_INFERRED = "E3_INFERRED"
    E4_HYPOTHETICAL = "E4_HYPOTHETICAL"


@dataclass(frozen=True)
class SourceRecord:
    source: str
    source_type: str
    capability: str
    topic: str
    payload: Mapping[str, Any]
    evidence_grade: EvidenceGrade = EvidenceGrade.E0_DIRECT
    reliability: float = 1.0
    evidence_id: str = ""
    artifact_ref: str = ""

    def __post_init__(self):
        if not self.source or not self.source_type or not self.capability or not self.topic:
            raise ValueError("source provenance fields are required")
        if not 0.0 <= self.reliability <= 1.0:
            raise ValueError("reliability must be between 0 and 1")


class InternalSourceAdapter:
    def normalize(self, record: SourceRecord, *, task_id: str, trace_id: str) -> KIPEnvelope:
        if not task_id or not trace_id:
            raise ValueError("task_id and trace_id are required")
        payload = dict(record.payload)
        payload.setdefault("source_type", record.source_type)
        payload.setdefault("capability", record.capability)
        return KIPEnvelope(
            kind="observation", topic=record.topic, source=record.source,
            task_id=task_id, trace_id=trace_id, payload=payload,
            reliability=record.reliability, evidence_grade=record.evidence_grade.value,
            evidence_id=record.evidence_id, provenance={
                "source_type": record.source_type, "capability": record.capability,
                "artifact_ref": record.artifact_ref,
            },
        )
