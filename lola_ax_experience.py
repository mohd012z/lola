"""Cross-agent (AX) contextual experience aggregation with lineage-aware counts."""
from dataclasses import dataclass

@dataclass(frozen=True)
class AXExperience:
    agent_id: str
    domain: str
    problem_class: str
    episode_count: int
    verified_count: int
    failure_count: int
    independent_origins: tuple
    independent_origin_count: int
    mean_information_gain: float

def aggregate_ax(episodes):
    groups={}
    for e in episodes:
        key=(str(e.get("agent_id","")),str(e.get("domain","")),str(e.get("problem_class","")))
        groups.setdefault(key,[]).append(e)
    out=[]
    for key in sorted(groups):
        es=groups[key]; n=len(es)
        roots=tuple(sorted({str(r) for e in es for r in (e.get("origin_roots") or ()) if r}))
        verified=sum(str(e.get("outcome",""))=="VERIFIED" for e in es)
        failed=sum(str(e.get("outcome","")) in {"FAILED","FALSIFIED"} for e in es)
        ig=sum(float(e.get("information_gain",0) or 0) for e in es)/n
        out.append(AXExperience(key[0],key[1],key[2],n,verified,failed,roots,len(roots),ig))
    return tuple(out)
