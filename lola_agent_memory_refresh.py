"""Plan agent-memory refreshes without silently reviving stale or quarantined knowledge."""
from dataclasses import dataclass
from lola_stale_memory_detector import detect_stale_memory
from lola_memory_retrieval import retrieve_knowledge

@dataclass(frozen=True)
class AgentMemoryRefresh:
    status: str
    refreshes: tuple
    blocked_ids: tuple
    execution_authority: bool = False

def refresh_agent_memory(records, snapshot):
    refreshes=[]; blocked=[]
    for knowledge_id,version in sorted(snapshot.items(),key=lambda x:str(x[0])):
        stale=detect_stale_memory(records,knowledge_id,version)
        if not stale.stale:
            continue
        latest=retrieve_knowledge(records,knowledge_id)
        if latest.status=="HIT" and latest.version is not None:
            refreshes.append((str(knowledge_id),int(version),int(latest.version)))
        else:
            blocked.append(str(knowledge_id))
    if blocked:
        status="BLOCKED"
    elif refreshes:
        status="REFRESH_REQUIRED"
    else:
        status="CURRENT"
    return AgentMemoryRefresh(status,tuple(refreshes),tuple(blocked),False)
