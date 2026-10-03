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
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_OPTIONS_BYTES = 64 * 1024


class ProtocolError(ValueError):
    pass


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

    def validate(self) -> None:
        if not self.path or "\x00" in self.path:
            raise ProtocolError("source path is empty or contains NUL")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in self.sha256):
            raise ProtocolError("source sha256 must be 64 hexadecimal characters")
        if self.size < 0 or self.size > MAX_SOURCE_BYTES:
            raise ProtocolError("source size is outside the allowed boundary")


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

    def validate(self) -> None:
        if self.protocol != PROTOCOL_VERSION:
            raise ProtocolError(f"unsupported protocol: {self.protocol}")
        self.source.validate()
        for name, value in (("request_id", self.request_id), ("run_id", self.run_id)):
            if not value or len(value) > 128 or "\x00" in value:
                raise ProtocolError(f"invalid {name}")
        try:
            encoded = json.dumps(self.options, sort_keys=True, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ProtocolError("options must be JSON serializable") from exc
        if len(encoded) > MAX_OPTIONS_BYTES:
            raise ProtocolError("options exceed the allowed boundary")


@dataclass(frozen=True)
class WorkerFinding:
    worker: str
    kind: str
    score: float
    locator: str
    detail: str = ""

    def validate(self) -> None:
        if not self.worker or not self.kind:
            raise ProtocolError("worker finding requires worker and kind")
        if not 0.0 <= float(self.score) <= 1.0:
            raise ProtocolError("worker score must be between 0 and 1")


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

    def validate(self) -> None:
        if not self.worker:
            raise ProtocolError("worker result requires worker identity")
        if len(self.source_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in self.source_sha256):
            raise ProtocolError("worker result has invalid source sha256")
        for finding in self.findings:
            finding.validate()
