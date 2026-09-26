#!/usr/bin/env python3
"""Evidence ledger and confidence model for Lola analysis.

This module is deliberately analysis-only: it records observations and provenance,
then derives confidence without performing target modification or exploitation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
import hashlib
import json


class Confidence(str, Enum):
    VERIFIED = "VERIFIED"
    HIGH = "HIGH"
    PROBABLE = "PROBABLE"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Evidence:
    kind: str
    source: str
    observation: str
    locator: str = ""
    tool: str = "lola"
    weight: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def normalized_weight(self) -> float:
        return max(0.0, min(1.0, float(self.weight)))


@dataclass
class Finding:
    finding_id: str
    statement: str
    evidence: list[Evidence] = field(default_factory=list)
    contradictions: list[Evidence] = field(default_factory=list)

    def confidence_score(self) -> float:
        if not self.evidence:
            return 0.0
        positive = sum(x.normalized_weight() for x in self.evidence)
        negative = sum(x.normalized_weight() for x in self.contradictions)
        diversity = min(1.0, len({(x.kind, x.tool) for x in self.evidence}) / 3.0)
        raw = (positive - negative) / max(1.0, positive + negative)
        return max(0.0, min(1.0, 0.8 * raw + 0.2 * diversity))

    def confidence(self) -> Confidence:
        score = self.confidence_score()
        independent = len({(x.kind, x.tool, x.source) for x in self.evidence})
        if score >= 0.90 and independent >= 2:
            return Confidence.VERIFIED
        if score >= 0.75:
            return Confidence.HIGH
        if score >= 0.55:
            return Confidence.PROBABLE
        if score > 0.0:
            return Confidence.INFERRED
        return Confidence.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.finding_id,
            "statement": self.statement,
            "confidence": self.confidence().value,
            "score": round(self.confidence_score(), 4),
            "evidence": [asdict(x) for x in self.evidence],
            "contradictions": [asdict(x) for x in self.contradictions],
        }


class EvidenceLedger:
    def __init__(self, target: str | Path):
        self.target = str(target)
        self.findings: dict[str, Finding] = {}

    @staticmethod
    def make_id(statement: str) -> str:
        return hashlib.sha256(statement.encode("utf-8")).hexdigest()[:16]

    def finding(self, statement: str, finding_id: str | None = None) -> Finding:
        fid = finding_id or self.make_id(statement)
        if fid not in self.findings:
            self.findings[fid] = Finding(fid, statement)
        return self.findings[fid]

    def add(self, statement: str, evidence: Evidence, *, contradiction: bool = False) -> Finding:
        item = self.finding(statement)
        bucket = item.contradictions if contradiction else item.evidence
        if evidence not in bucket:
            bucket.append(evidence)
        return item

    def summary(self) -> dict[str, Any]:
        counts = {x.value: 0 for x in Confidence}
        for finding in self.findings.values():
            counts[finding.confidence().value] += 1
        return {
            "target": self.target,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "counts": counts,
            "findings": [x.to_dict() for x in self.findings.values()],
        }

    def write(self, output: str | Path) -> Path:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.summary(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path
