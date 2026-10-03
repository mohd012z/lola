"""Pure atomic knowledge transaction: validate version, activate candidate, supersede prior version, or roll back."""
from dataclasses import dataclass

@dataclass(frozen=True)
class KnowledgeTransactionResult:
    status: str
    history: tuple
    reason: str
    execution_authority: bool = False

def commit_candidate(history,candidate):
    original=tuple(dict(r) for r in history)
    if getattr(candidate,"status",None)!="CANDIDATE" or candidate.version is None:
        return KnowledgeTransactionResult("REJECTED",original,"INVALID_CANDIDATE",False)
    kid=str(candidate.knowledge_id)
    relevant=[r for r in original if str(r.get("knowledge_id",""))==kid]
    current=max((int(r["version"]) for r in relevant),default=0)
    expected_previous=candidate.supersedes_version or 0
    if current!=expected_previous or int(candidate.version)!=current+1:
        return KnowledgeTransactionResult("ROLLED_BACK",original,"VERSION_CONFLICT",False)
    active=[r for r in relevant if r.get("state")=="ACTIVE"]
    if current and (len(active)!=1 or int(active[0]["version"])!=current):
        return KnowledgeTransactionResult("ROLLED_BACK",original,"ACTIVE_STATE_CONFLICT",False)
    staged=[]
    for row in original:
        item=dict(row)
        if str(item.get("knowledge_id",""))==kid and current and int(item.get("version",0))==current:
            item["state"]="SUPERSEDED"
        staged.append(item)
    staged.append({"knowledge_id":kid,"version":int(candidate.version),"state":"ACTIVE","supersedes_version":candidate.supersedes_version,"payload":candidate.payload,"episode_ids":list(candidate.episode_ids),"evidence_ids":list(candidate.evidence_ids),"trace_id":candidate.trace_id,"fingerprint":candidate.fingerprint})
    return KnowledgeTransactionResult("COMMITTED",tuple(staged),"ATOMIC_VERSION_ADVANCE",False)
