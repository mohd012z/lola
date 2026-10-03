#!/usr/bin/env python3
"""Tamper-evident append-only evidence core for LOLA."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib, json
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

GENESIS_HASH = "0" * 64

def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def event_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()

@dataclass(frozen=True)
class EvidenceEvent:
    event_id: str
    trace_id: str
    timestamp: str
    event_type: str
    source_hash: str
    decision: str | None
    details: dict[str, Any]
    previous_hash: str
    event_hash: str
    def to_dict(self): return asdict(self)

class EvidenceIntegrityError(ValueError): pass

class EvidenceCoreLedger:
    def __init__(self, path: str | Path): self.path = Path(path)

    def _raw(self):
        if not self.path.exists(): return []
        out=[]
        for n,line in enumerate(self.path.read_text(encoding="utf-8").splitlines(),1):
            if not line.strip(): continue
            try: value=json.loads(line)
            except json.JSONDecodeError as exc: raise EvidenceIntegrityError(f"invalid JSON at line {n}") from exc
            if not isinstance(value,dict): raise EvidenceIntegrityError(f"non-object event at line {n}")
            out.append(value)
        return out

    @staticmethod
    def verify_events(events: Iterable[dict[str, Any]]):
        result=[]; previous=GENESIS_HASH; ids=set()
        required={"event_id","trace_id","timestamp","event_type","source_hash","decision","details","previous_hash","event_hash"}
        for n,raw in enumerate(events,1):
            if set(raw)!=required: raise EvidenceIntegrityError(f"invalid schema at event {n}")
            if raw["event_id"] in ids: raise EvidenceIntegrityError(f"duplicate event_id at event {n}")
            if raw["previous_hash"]!=previous: raise EvidenceIntegrityError(f"broken hash chain at event {n}")
            unsigned=dict(raw); claimed=unsigned.pop("event_hash")
            if event_digest(unsigned)!=claimed: raise EvidenceIntegrityError(f"event hash mismatch at event {n}")
            ids.add(raw["event_id"]); previous=claimed; result.append(EvidenceEvent(**raw))
        return result

    def verify(self): return self.verify_events(self._raw())

    def append(self, *, trace_id: str, event_type: str, source_hash: str, decision: str | None=None, details: dict[str,Any] | None=None, event_id: str | None=None, timestamp: str | None=None):
        current=self.verify()
        unsigned={"event_id":event_id or str(uuid4()),"trace_id":trace_id,"timestamp":timestamp or datetime.now(timezone.utc).isoformat(),"event_type":event_type,"source_hash":source_hash,"decision":decision,"details":details or {},"previous_hash":current[-1].event_hash if current else GENESIS_HASH}
        event=EvidenceEvent(**unsigned,event_hash=event_digest(unsigned))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open("a",encoding="utf-8",newline="\n") as f: f.write(canonical_json(event.to_dict())+"\n"); f.flush()
        return event

    def trace(self, trace_id: str): return [x for x in self.verify() if x.trace_id==trace_id]
