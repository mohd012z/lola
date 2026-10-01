"""Conservative adaptive consolidation decision over recurrence, lineage and falsification state."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ConsolidationDecision:
    status: str
    reason: str
    execution_authority: bool = False

def consolidation_decision(*,recurrence,independent_origins,counterexamples,unknowns,transfer_supported,requires_transfer=False):
    vals=[recurrence,independent_origins,counterexamples,unknowns]
    if any(int(v)<0 for v in vals): raise ValueError("counts must be non-negative")
    if counterexamples: return ConsolidationDecision("REJECT","counterexamples_present",False)
    if unknowns: return ConsolidationDecision("DEFER","unknowns_unresolved",False)
    if recurrence<2: return ConsolidationDecision("DEFER","insufficient_recurrence",False)
    if independent_origins<2: return ConsolidationDecision("DEFER","insufficient_independence",False)
    if requires_transfer and not transfer_supported: return ConsolidationDecision("DEFER","transfer_not_supported",False)
    return ConsolidationDecision("CANDIDATE","ready_for_governance",False)
