"""Compare old/new hypothesis conclusions after selective replay."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ReasoningDelta:
    changed_hypothesis_ids: tuple
    unchanged_hypothesis_ids: tuple
    unresolved_hypothesis_ids: tuple
    recheck_required: bool
    execution_authority: bool = False

def compare_reasoning(before, after, replay_hypothesis_ids):
    replay={str(x) for x in replay_hypothesis_ids}
    changed=[]; unresolved=[]
    for hid in sorted(replay):
        if hid not in after:
            unresolved.append(hid)
        elif before.get(hid) != after.get(hid):
            changed.append(hid)
    all_ids={str(x) for x in before} | {str(x) for x in after}
    unchanged=tuple(sorted(hid for hid in all_ids if hid not in changed and hid not in unresolved and before.get(hid)==after.get(hid)))
    return ReasoningDelta(tuple(changed),unchanged,tuple(unresolved),bool(changed or unresolved),False)
