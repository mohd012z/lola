"""Prepare validated knowledge consolidation candidates without granting execution authority."""
from dataclasses import dataclass
import hashlib
import json

@dataclass(frozen=True)
class ConsolidationCandidate:
    status: str
    knowledge_id: str
    version: int | None
    supersedes_version: int | None
    payload: object
    episode_ids: tuple
    evidence_ids: tuple
    trace_id: str
    fingerprint: str
    execution_authority: bool = False

def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),default=str)

def _fingerprint(knowledge_id,payload,episode_ids,evidence_ids,trace_id):
    raw="|".join((str(knowledge_id),_canonical(payload),_canonical(episode_ids),_canonical(evidence_ids),str(trace_id)))
    return hashlib.sha256(raw.encode()).hexdigest()

def prepare_consolidation(*,history,knowledge_id,payload,release_status,episode_ids,evidence_ids,trace_id):
    kid=str(knowledge_id); tid=str(trace_id)
    episodes=tuple(sorted({str(x) for x in episode_ids if x}))
    evidence=tuple(sorted({str(x) for x in evidence_ids if x}))
    fp=_fingerprint(kid,payload,episodes,evidence,tid)
    if release_status != "RELEASE_CANDIDATE":
        return ConsolidationCandidate("BLOCKED",kid,None,None,payload,episodes,evidence,tid,fp,False)
    relevant=[r for r in history if str(r.get("knowledge_id",""))==kid]
    for r in relevant:
        rfp=_fingerprint(kid,r.get("payload"),tuple(sorted(r.get("episode_ids",()))),tuple(sorted(r.get("evidence_ids",()))),r.get("trace_id",""))
        if rfp==fp:
            return ConsolidationCandidate("DUPLICATE",kid,None,None,payload,episodes,evidence,tid,fp,False)
    previous=max((int(r["version"]) for r in relevant),default=0)
    version=previous+1
    return ConsolidationCandidate("CANDIDATE",kid,version,previous or None,payload,episodes,evidence,tid,fp,False)
