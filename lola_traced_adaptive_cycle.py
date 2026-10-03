"""Execute the adaptive cognitive cycle while emitting and verifying its deterministic trace."""
from dataclasses import dataclass
from lola_adaptive_cycle_orchestrator import orchestrate_adaptive_cycle
from lola_agent_memory_refresh import refresh_agent_memory
from lola_trace_ledger import TraceLedger
from lola_trace_replay import verify_trace

@dataclass(frozen=True)
class TracedAdaptiveCycleResult:
    cycle: object
    entries: tuple
    verification: object
    execution_authority: bool = False

def run_traced_adaptive_cycle(*,records,snapshot,dependencies,before,after,contradictions,unknowns,trace_id):
    cycle=orchestrate_adaptive_cycle(records=records,snapshot=snapshot,dependencies=dependencies,before=before,after=after,contradictions=contradictions,unknowns=unknowns,trace_id=trace_id)
    ledger=TraceLedger(trace_id)
    refresh=refresh_agent_memory(records,snapshot)
    ledger=ledger.append("MEMORY_REFRESH",{"status":refresh.status,"refreshes":refresh.refreshes,"blocked_ids":refresh.blocked_ids})
    if cycle.status!="BLOCKED" or cycle.recommendation!="REFRESH_BLOCKED":
        ledger=ledger.append("DEPENDENCY_REPLAY",{"changed_knowledge_ids":cycle.changed_knowledge_ids,"replay_hypothesis_ids":cycle.replay_hypothesis_ids})
        ledger=ledger.append("REASONING_DELTA",{"changed_hypothesis_ids":cycle.changed_hypothesis_ids,"unresolved_hypothesis_ids":cycle.unresolved_hypothesis_ids})
        ledger=ledger.append("FEEDBACK",{"status":cycle.status,"recommendation":cycle.recommendation})
    verification=verify_trace(str(trace_id),ledger.entries)
    return TracedAdaptiveCycleResult(cycle,ledger.entries,verification,False)
