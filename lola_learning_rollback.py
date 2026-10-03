"""Non-destructive rollback planning for learned candidates and dependent artifacts."""
from dataclasses import dataclass

@dataclass(frozen=True)
class RollbackPlan:
    candidate_id: str
    status: str
    reason: str
    affected_artifact_ids: tuple
    execution_authority: bool = False

def rollback_plan(candidate_id,affected_artifact_ids,*,reason):
    affected=tuple(dict.fromkeys(map(str,affected_artifact_ids)))
    status="QUARANTINE" if affected else "REVIEW"
    return RollbackPlan(str(candidate_id),status,str(reason),affected,False)
