"""Lifecycle-aware retrieval: never silently fall back to superseded knowledge."""
from dataclasses import dataclass
from typing import Any
from lola_knowledge_lifecycle import KnowledgeVersion, KnowledgeLifecycle

@dataclass(frozen=True)
class RetrievalResult:
    knowledge_id: str
    version: int | None
    status: str
    payload: Any = None
    execution_authority: bool = False

def retrieve_knowledge(records, knowledge_id):
    kid=str(knowledge_id)
    relevant=[r for r in records if str(r.get("knowledge_id",""))==kid]
    if not relevant:
        return RetrievalResult(kid,None,"MISS",None,False)
    versions=tuple(KnowledgeVersion(kid,int(r["version"]),str(r["state"]),r.get("supersedes_version")) for r in relevant)
    lifecycle=KnowledgeLifecycle(versions)
    latest=max(relevant,key=lambda r:int(r["version"]))
    version=int(latest["version"])
    if not lifecycle.usable(kid,version):
        return RetrievalResult(kid,version,"BLOCKED",None,False)
    return RetrievalResult(kid,version,"HIT",latest.get("payload"),False)
