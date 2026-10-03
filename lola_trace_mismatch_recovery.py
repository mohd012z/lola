"""Convert trace verification failures into conservative, targeted recovery plans."""
from dataclasses import dataclass
from lola_trace_replay import verify_trace

@dataclass(frozen=True)
class TraceRecoveryAssessment:
    status: str
    quarantine: bool
    replay_from_sequence: int | None
    checked_entries: int
    recommendation: str
    execution_authority: bool = False

def assess_trace_recovery(trace_id, entries):
    verification=verify_trace(str(trace_id),tuple(entries))
    if verification.valid:
        return TraceRecoveryAssessment("VERIFIED",False,None,verification.checked_entries,"CONTINUE",False)
    sequence=verification.mismatch_sequence or 1
    return TraceRecoveryAssessment("QUARANTINED",True,sequence,verification.checked_entries,"REPLAY_DIVERGENT_SUFFIX",False)
