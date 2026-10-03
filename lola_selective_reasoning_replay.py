"""Dependency-aware replay planner: revisit only hypotheses affected by changed knowledge."""
from dataclasses import dataclass

@dataclass(frozen=True)
class SelectiveReplayPlan:
    status: str
    replay_hypothesis_ids: tuple
    untouched_hypothesis_ids: tuple
    changed_knowledge_ids: tuple
    execution_authority: bool = False

def plan_selective_replay(hypothesis_dependencies, changed_knowledge_ids):
    changed=tuple(sorted({str(x) for x in changed_knowledge_ids if x}))
    changed_set=set(changed)
    replay=[]; untouched=[]
    for hypothesis_id,deps in sorted(hypothesis_dependencies.items(),key=lambda x:str(x[0])):
        hid=str(hypothesis_id)
        dep_set={str(x) for x in (deps or ()) if x}
        if dep_set & changed_set:
            replay.append(hid)
        else:
            untouched.append(hid)
    status="REPLAY_REQUIRED" if replay else "NO_REPLAY"
    return SelectiveReplayPlan(status,tuple(replay),tuple(untouched),changed,False)
