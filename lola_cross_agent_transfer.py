"""Conservative cross-agent/context transfer evidence assessment."""
from dataclasses import dataclass

@dataclass(frozen=True)
class TransferAssessment:
    transfer_supported: bool
    verified_episode_ids: tuple
    context_fingerprints: tuple
    agent_ids: tuple
    independent_origins: tuple
    independent_origin_count: int

def assess_transfer(episodes):
    verified=tuple(e for e in episodes if str(e.get("outcome",""))=="VERIFIED")
    ids=tuple(sorted(str(e.get("episode_id","")) for e in verified))
    contexts=tuple(sorted({str(e.get("context_fingerprint","")) for e in verified if e.get("context_fingerprint")}))
    agents=tuple(sorted({str(e.get("agent_id","")) for e in verified if e.get("agent_id")}))
    origins=tuple(sorted({str(o) for e in verified for o in (e.get("origin_roots") or ()) if o}))
    supported=len(ids)>=2 and len(contexts)>=2 and len(agents)>=2 and len(origins)>=2
    return TransferAssessment(supported,ids,contexts,agents,origins,len(origins))
