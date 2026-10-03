"""Transfer-aware AR1 governance; advisory evidence never grants action authority."""
from dataclasses import dataclass
from lola_agent_consolidation import govern_agent_candidate

@dataclass(frozen=True)
class TransferGovernanceResult:
    promotable: bool
    reason: str
    execution_authority: bool = False

def govern_transfer_routing(supporting_episode_ids, independent_origin_domains, counterexample_episode_ids, applicability, *, transfer_supported):
    base=govern_agent_candidate("AR1",supporting_episode_ids,independent_origin_domains,counterexample_episode_ids,applicability=applicability)
    if not base.promotable:
        return TransferGovernanceResult(False,base.reason,False)
    if not transfer_supported:
        return TransferGovernanceResult(False,"transfer_not_supported",False)
    return TransferGovernanceResult(True,"governance_passed",False)
