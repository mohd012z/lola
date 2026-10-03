"""End-to-end controller for trace recovery, quarantine, L5 recheck and consolidation release candidacy."""
from dataclasses import dataclass
from lola_trace_mismatch_recovery import assess_trace_recovery
from lola_suffix_recovery_executor import recover_trace_suffix
from lola_quarantine_release_gate import assess_quarantine_release

@dataclass(frozen=True)
class RecoveryConsolidationResult:
    status: str
    reason: str
    quarantine: bool
    replay_from_sequence: int | None
    entries: tuple
    execution_authority: bool = False

def control_recovery(*,trace_id,entries,replacement_stages,changed_hypotheses,unresolved_hypotheses,contradictions,unknowns):
    original=tuple(entries)
    recovery=assess_trace_recovery(trace_id,original)
    active_entries=original
    replay_from=None
    if recovery.quarantine:
        replay_from=recovery.replay_from_sequence
        if replacement_stages is None:
            return RecoveryConsolidationResult("QUARANTINED","TRACE_MISMATCH",True,replay_from,active_entries,False)
        rebuilt=recover_trace_suffix(trace_id,original,replay_from,replacement_stages)
        if not rebuilt.verification.valid:
            return RecoveryConsolidationResult("QUARANTINED","RECOVERY_UNVERIFIED",True,replay_from,rebuilt.entries,False)
        active_entries=rebuilt.entries
    release=assess_quarantine_release(trace_verified=True,changed_hypotheses=changed_hypotheses,unresolved_hypotheses=unresolved_hypotheses,contradictions=contradictions,unknowns=unknowns)
    reason={"RELEASE_CANDIDATE":"STABLE_EVIDENCE","RECHECK":"L5_RECHECK_REQUIRED","QUARANTINED":release.recommendation}.get(release.status,release.recommendation)
    return RecoveryConsolidationResult(release.status,reason,release.quarantine,replay_from,active_entries,False)
