"""Immutable-style deterministic trace ledger for adaptive cognitive stages."""
from dataclasses import dataclass
import hashlib
import json

@dataclass(frozen=True)
class TraceEntry:
    trace_id: str
    sequence: int
    stage: str
    payload: dict
    digest: str

class TraceLedger:
    def __init__(self,trace_id,entries=()):
        if not str(trace_id): raise ValueError("trace_id required")
        self.trace_id=str(trace_id)
        self.entries=tuple(entries)
    def append(self,stage,payload):
        stage=str(stage)
        normalized=json.dumps(payload or {},sort_keys=True,separators=(",",":"),default=str)
        previous=self.entries[-1].digest if self.entries else "GENESIS"
        raw=f"{self.trace_id}|{len(self.entries)+1}|{stage}|{normalized}|{previous}".encode()
        digest=hashlib.sha256(raw).hexdigest()
        entry=TraceEntry(self.trace_id,len(self.entries)+1,stage,dict(payload or {}),digest)
        return TraceLedger(self.trace_id,self.entries+(entry,))
