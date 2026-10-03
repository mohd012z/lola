"""Reconstruct and verify deterministic cognitive trace chains."""
from dataclasses import dataclass
from lola_trace_ledger import TraceLedger

@dataclass(frozen=True)
class TraceVerification:
    valid: bool
    status: str
    checked_entries: int
    mismatch_sequence: int | None = None
    execution_authority: bool = False

def verify_trace(trace_id, entries):
    tid=str(trace_id)
    if not tid:
        return TraceVerification(False,"INVALID_TRACE_ID",0,None,False)
    rebuilt=TraceLedger(tid)
    checked=0
    for expected_sequence,entry in enumerate(entries,start=1):
        if entry.trace_id != tid or entry.sequence != expected_sequence:
            return TraceVerification(False,"MISMATCH",checked,expected_sequence,False)
        rebuilt=rebuilt.append(entry.stage,entry.payload)
        checked+=1
        if rebuilt.entries[-1].digest != entry.digest:
            return TraceVerification(False,"MISMATCH",checked,expected_sequence,False)
    return TraceVerification(True,"VERIFIED",checked,None,False)
