"""Detect references to superseded, quarantined or rejected learned knowledge."""
from dataclasses import dataclass
from lola_knowledge_lifecycle import KnowledgeVersion, KnowledgeLifecycle

@dataclass(frozen=True)
class StaleMemoryAssessment:
    knowledge_id: str
    version: int
    stale: bool
    reason: str
    execution_authority: bool = False

def detect_stale_memory(records, knowledge_id, version):
    kid=str(knowledge_id); ver=int(version)
    relevant=[r for r in records if str(r.get("knowledge_id",""))==kid]
    if not relevant:
        return StaleMemoryAssessment(kid,ver,True,"MISSING",False)
    versions=tuple(KnowledgeVersion(kid,int(r["version"]),str(r["state"]),r.get("supersedes_version")) for r in relevant)
    lifecycle=KnowledgeLifecycle(versions)
    try:
        status=lifecycle.status(kid,ver)
    except KeyError:
        return StaleMemoryAssessment(kid,ver,True,"MISSING_VERSION",False)
    stale=status!="ACTIVE"
    return StaleMemoryAssessment(kid,ver,stale,status if stale else "CURRENT",False)
