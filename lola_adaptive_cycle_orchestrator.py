"""Deterministic Kernel/IN_AI adaptive-cycle orchestration with an auditable trace id."""
from dataclasses import dataclass
from lola_agent_memory_refresh import refresh_agent_memory
from lola_selective_reasoning_replay import plan_selective_replay
from lola_reasoning_delta import compare_reasoning
from lola_feedback_loop import evaluate_feedback

@dataclass(frozen=True)
class AdaptiveCycleResult:
    trace_id: str
    status: str
    recommendation: str
    changed_knowledge_ids: tuple
    replay_hypothesis_ids: tuple
    changed_hypothesis_ids: tuple
    unresolved_hypothesis_ids: tuple
    execution_authority: bool = False

def orchestrate_adaptive_cycle(*,records,snapshot,dependencies,before,after,contradictions,unknowns,trace_id):
    tid=str(trace_id)
    if not tid:
        raise ValueError("trace_id required")
    refresh=refresh_agent_memory(records,snapshot)
    if refresh.status=="BLOCKED":
        return AdaptiveCycleResult(tid,"BLOCKED","REFRESH_BLOCKED",(),(),(),(),False)
    changed=tuple(sorted({kid for kid,old,new in refresh.refreshes if old!=new}))
    replay=plan_selective_replay(dependencies,changed)
    delta=compare_reasoning(before,after,replay.replay_hypothesis_ids)
    feedback=evaluate_feedback(changed_hypotheses=delta.changed_hypothesis_ids,unresolved_hypotheses=delta.unresolved_hypothesis_ids,contradictions=contradictions,unknowns=unknowns)
    return AdaptiveCycleResult(tid,feedback.status,feedback.recommendation,changed,replay.replay_hypothesis_ids,delta.changed_hypothesis_ids,delta.unresolved_hypothesis_ids,False)
