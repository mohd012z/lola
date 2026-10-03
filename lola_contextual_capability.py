"""Contextual capability aggregation using inspectable raw components."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ContextualCapability:
    agent_id: str
    domain: str
    problem_class: str
    context_key: str
    attempts: int
    verified_attempts: int
    recovered_attempts: int
    failures: int
    mean_information_gain: float
    duplicate_probe_rate: float
    mean_cost: float
    mean_latency: float

def aggregate_capability(records):
    groups={}
    for r in records:
        key=(str(r.get("agent_id","")),str(r.get("domain","")),str(r.get("problem_class","")))
        groups.setdefault(key,[]).append(r)
    out=[]
    for key in sorted(groups):
        rs=groups[key]; n=len(rs)
        mean=lambda name: sum(float(r.get(name,0) or 0) for r in rs)/n
        verified=sum(str(r.get("outcome",""))=="VERIFIED" for r in rs)
        recovered=sum(bool(r.get("recovered")) for r in rs)
        failures=sum(str(r.get("outcome","")) in {"FAILED","FALSIFIED"} for r in rs)
        dup=sum(bool(r.get("duplicate_probe")) for r in rs)/n
        context_key="|".join(key)
        out.append(ContextualCapability(key[0],key[1],key[2],context_key,n,verified,recovered,failures,mean("information_gain"),dup,mean("cost"),mean("latency")))
    return tuple(out)
