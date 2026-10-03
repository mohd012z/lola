"""Kernel/IN_AI cognitive-cycle gate connecting metacognition to governed consolidation."""
from dataclasses import dataclass
from lola_metacognitive_controller import assess_reasoning_state
from lola_adaptive_consolidation import consolidation_decision

@dataclass(frozen=True)
class CognitiveCycleResult:
    metacognitive_recommendation: str
    reasoning_ready: bool
    consolidation_status: str
    consolidation_reason: str
    execution_authority: bool = False

def run_cognitive_cycle(*,evidence_count,independent_origins,contradictions,unknowns,failed_replays,recurrence,counterexamples,transfer_supported,requires_transfer=False):
    meta=assess_reasoning_state(evidence_count=evidence_count,independent_origins=independent_origins,contradictions=contradictions,unknowns=unknowns,failed_replays=failed_replays)
    if not meta.action_ready:
        return CognitiveCycleResult(meta.recommendation,False,"BLOCKED","metacognitive_gate",False)
    decision=consolidation_decision(recurrence=recurrence,independent_origins=independent_origins,counterexamples=counterexamples,unknowns=unknowns,transfer_supported=transfer_supported,requires_transfer=requires_transfer)
    return CognitiveCycleResult(meta.recommendation,True,decision.status,decision.reason,False)
