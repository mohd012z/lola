"""Revision-aware cognitive cycle: preserve history, quarantine invalid learning, then re-evaluate."""
from dataclasses import dataclass
from lola_revision_engine import revise_candidate
from lola_learning_rollback import rollback_plan
from lola_cognitive_cycle import run_cognitive_cycle

@dataclass(frozen=True)
class RevisionCycleResult:
    revision_status: str
    rollback_action: str
    cognitive_status: str
    cognitive_reason: str
    execution_authority: bool = False

def run_revision_cycle(*,candidate_id,assumptions,invalid_assumption_ids,supporting_evidence_ids,counterexample_evidence_ids,evidence_count,independent_origins,contradictions,unknowns,failed_replays,recurrence,counterexamples,transfer_supported,requires_transfer=False):
    needs_revision=bool(invalid_assumption_ids or counterexample_evidence_ids or failed_replays or contradictions)
    if needs_revision:
        revision=revise_candidate("LEARNED",assumptions,invalid_assumption_ids,supporting_evidence_ids,counterexample_evidence_ids)
        affected=(candidate_id,) if revision.status=="REVISION_REQUIRED" or failed_replays or contradictions else ()
        rollback=rollback_plan(candidate_id,affected,reason="reasoning_invalidated")
        return RevisionCycleResult("REVISED",rollback.status,"BLOCKED","revision_requires_replay",False)
    cognitive=run_cognitive_cycle(evidence_count=evidence_count,independent_origins=independent_origins,contradictions=contradictions,unknowns=unknowns,failed_replays=failed_replays,recurrence=recurrence,counterexamples=counterexamples,transfer_supported=transfer_supported,requires_transfer=requires_transfer)
    return RevisionCycleResult("NOT_REQUIRED","NONE",cognitive.consolidation_status,cognitive.consolidation_reason,False)
