"""Tamper-evident event chain for Lola guardrail evidence.

This supplements, rather than replaces, Lola's EvidenceLedger. Events are
canonicalized and SHA-256 chained so stored guardrail traces can be verified
for accidental or unauthorized mutation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable

GENESIS = "0" * 64


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class ChainEvent:
    sequence: int
    stage: str
    source_sha256: str
    payload: dict[str, Any]
    parent_sha256: str
    timestamp: str
    event_sha256: str

    def unsigned(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("event_sha256")
        return data

    def verify_hash(self) -> bool:
        return hashlib.sha256(_canonical(self.unsigned())).hexdigest() == self.event_sha256


class EvidenceChain:
    def __init__(self) -> None:
        self._events: list[ChainEvent] = []

    @property
    def events(self) -> tuple[ChainEvent, ...]:
        return tuple(self._events)

    @property
    def head(self) -> str:
        return self._events[-1].event_sha256 if self._events else GENESIS

    def append(
        self,
        stage: str,
        source_sha256: str,
        payload: dict[str, Any],
        *,
        timestamp: str | None = None,
    ) -> ChainEvent:
        unsigned = {
            "sequence": len(self._events),
            "stage": str(stage),
            "source_sha256": str(source_sha256),
            "payload": dict(payload),
            "parent_sha256": self.head,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        }
        digest = hashlib.sha256(_canonical(unsigned)).hexdigest()
        event = ChainEvent(event_sha256=digest, **unsigned)
        self._events.append(event)
        return event

    @staticmethod
    def verify(events: Iterable[ChainEvent]) -> bool:
        parent = GENESIS
        expected_sequence = 0
        for event in events:
            if event.sequence != expected_sequence:
                return False
            if event.parent_sha256 != parent:
                return False
            if not event.verify_hash():
                return False
            parent = event.event_sha256
            expected_sequence += 1
        return True
