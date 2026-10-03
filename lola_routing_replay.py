"""Replay/falsification of advisory routing candidates against historical episodes."""
from dataclasses import dataclass

@dataclass(frozen=True)
class RoutingReplay:
    status: str
    support_count: int
    failure_count: int
    independent_support_origins: tuple
    execution_authority: bool = False

def replay_routing_candidate(sequence, episodes):
    target=tuple(map(str,sequence)); support=0; failures=0; roots=set()
    for e in episodes:
        if tuple(map(str,e.get("sequence") or ()))!=target: continue
        outcome=str(e.get("outcome",""))
        if outcome=="VERIFIED":
            support+=1; roots.update(str(x) for x in (e.get("independent_origins") or ()) if x)
        elif outcome in {"FAILED","FALSIFIED"}: failures+=1
    if failures: status="FALSIFIED"
    elif support>=2 and len(roots)>=2: status="SUPPORTED"
    else: status="INCONCLUSIVE"
    return RoutingReplay(status,support,failures,tuple(sorted(roots)),False)
