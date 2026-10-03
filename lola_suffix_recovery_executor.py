"""Rebuild only the divergent suffix of a cognitive trace while preserving its verified prefix."""
from dataclasses import dataclass
from lola_trace_ledger import TraceLedger
from lola_trace_replay import verify_trace

@dataclass(frozen=True)
class SuffixRecoveryResult:
    status: str
    entries: tuple
    verification: object
    replay_from_sequence: int
    execution_authority: bool = False

def recover_trace_suffix(trace_id, original_entries, replay_from_sequence, replacement_stages):
    tid=str(trace_id)
    original=tuple(original_entries)
    start=int(replay_from_sequence)
    if start < 1 or start > len(original)+1:
        raise ValueError("invalid replay_from_sequence")
    prefix=original[:start-1]
    prefix_check=verify_trace(tid,prefix)
    if not prefix_check.valid:
        raise ValueError("prefix is not verified")
    ledger=TraceLedger(tid,prefix)
    for stage,payload in replacement_stages:
        ledger=ledger.append(stage,payload)
    verification=verify_trace(tid,ledger.entries)
    status="RECOVERED" if verification.valid else "QUARANTINED"
    return SuffixRecoveryResult(status,ledger.entries,verification,start,False)
