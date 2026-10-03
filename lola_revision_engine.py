"""Revision engine preserving falsification evidence and invalidated assumptions."""
from dataclasses import dataclass

@dataclass(frozen=True)
class RevisionResult:
    candidate_type: str
    status: str
    retained_assumption_ids: tuple
    invalidated_assumption_ids: tuple
    supporting_evidence_ids: tuple
    preserved_counterexample_ids: tuple
    execution_authority: bool = False

def revise_candidate(candidate_type,assumption_ids,invalidated_assumption_ids,supporting_evidence_ids,counterexample_ids):
    assumptions=tuple(dict.fromkeys(map(str,assumption_ids)))
    invalid=tuple(x for x in dict.fromkeys(map(str,invalidated_assumption_ids)) if x in assumptions)
    retained=tuple(x for x in assumptions if x not in set(invalid))
    support=tuple(dict.fromkeys(map(str,supporting_evidence_ids)))
    counter=tuple(dict.fromkeys(map(str,counterexample_ids)))
    status="REVISION_REQUIRED" if invalid or counter else "UNCHANGED"
    return RevisionResult(str(candidate_type),status,retained,invalid,support,counter,False)
