"""Typed protocol schemas for Lola's defensive LLM-security pipeline.

The protocol is intentionally data-only: workers can report observations but
cannot authorize execution or mutate policy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import uuid


PROTOCOL_VERSION = "GRD/1"


class Operation(str, Enum):
    SCAN = "SCAN"
    EXTRACT = "EXTRACT"
    SEMANTIC = "SEMANTIC"
    VERIFY = "VERIFY"
    BENCHMARK = "BENCHMARK"


@dataclass(frozen=True)
class SourceRef:
    path: str
    sha256: str
    size: int = 0


@dataclass(frozen=True)
class GuardRequest:
    operation: Operation
    source: SourceRef
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    protocol: str = PROTOCOL_VERSION
    options: dict[str, object] = field(default_factory=dict)

    def canonical_bytes(self) -> bytes:
        data = asdict(self)
        data["operation"] = self.operation.value
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class WorkerFinding:
    worker: str
    kind: str
    score: float
    locator: str
    detail: str = ""


@dataclass(frozen=True)
class WorkerResult:
    request_id: str
    run_id: str
    source_sha256: str
    worker: str
    findings: tuple[WorkerFinding, ...] = ()
    worker_version: str = "1"

    @property
    def max_score(self) -> float:
        return max((f.score for f in self.findings), default=0.0)
