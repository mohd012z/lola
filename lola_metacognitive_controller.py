"""L5 metacognitive controller: inspect reasoning reliability without self-authorizing action."""
from dataclasses import dataclass

@dataclass(frozen=True)
class MetacognitiveAssessment:
    recommendation: str
    action_ready: bool
    evidence_count: int
    independent_origins: int
    contradictions: int
    unknowns: int
    failed_replays: int
    execution_authority: bool = False

def assess_reasoning_state(*,evidence_count,independent_origins,contradictions,unknowns,failed_replays):
    vals=[evidence_count,independent_origins,contradictions,unknowns,failed_replays]
    if any(int(v)<0 for v in vals): raise ValueError("counts must be non-negative")
    if failed_replays: rec="REVISE_MODEL"; ready=False
    elif contradictions: rec="RESOLVE_CONTRADICTION"; ready=False
    elif unknowns: rec="REDUCE_UNKNOWNS"; ready=False
    elif independent_origins<2: rec="SEEK_INDEPENDENT_EVIDENCE"; ready=False
    elif evidence_count<2: rec="GATHER_EVIDENCE"; ready=False
    else: rec="READY_FOR_GOVERNANCE"; ready=True
    return MetacognitiveAssessment(rec,ready,int(evidence_count),int(independent_origins),int(contradictions),int(unknowns),int(failed_replays),False)
