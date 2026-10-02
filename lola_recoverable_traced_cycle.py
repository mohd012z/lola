"""Adaptive cycle with trace verification and conservative mismatch quarantine."""
from dataclasses import dataclass
from lola_traced_adaptive_cycle import run_traced_adaptive_cycle
from lola_trace_mismatch_recovery import assess_trace_recovery

@dataclass(frozen=True)
class RecoverableTracedCycleResult:
    status: str
    entries: tuple
    quarantine: bool
    replay_from_sequence: int | None
    cycle: object
    execution_authority: bool = False

def run_recoverable_traced_cycle(*,records,snapshot,dependencies,before,after,contradictions,unknowns,trace_id,verification_entries=None):
    traced=run_traced_adaptive_cycle(records=records,snapshot=snapshot,dependencies=dependencies,before=before,after=after,contradictions=contradictions,unknowns=unknowns,trace_id=trace_id)
    entries=tuple(traced.entries if verification_entries is None else verification_entries)
    recovery=assess_trace_recovery(trace_id,entries)
    if recovery.quarantine:
        return RecoverableTracedCycleResult("QUARANTINED",entries,True,recovery.replay_from_sequence,traced.cycle,False)
    return RecoverableTracedCycleResult("VERIFIED",entries,False,None,traced.cycle,False)
