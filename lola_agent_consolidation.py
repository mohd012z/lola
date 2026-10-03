"""Governance boundary for agent-derived consolidation candidates."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Any, Tuple


@dataclass(frozen=True)
class AgentGovernanceResult:
    candidate_type: str
    promotable: bool
    reason: str
    supporting_episode_ids: Tuple[str, ...]
    independent_origin_domains: Tuple[str, ...]
    counterexample_episode_ids: Tuple[str, ...]
    applicability: Mapping[str, Any]
    execution_authority: bool = False


def govern_agent_candidate(candidate_type, supporting_episode_ids, independent_origin_domains, counterexample_episode_ids, *, applicability):
    support = tuple(dict.fromkeys(map(str, supporting_episode_ids)))
    origins = tuple(dict.fromkeys(map(str, independent_origin_domains)))
    counterexamples = tuple(dict.fromkeys(map(str, counterexample_episode_ids)))
    if not applicability:
        return AgentGovernanceResult(str(candidate_type), False, "missing_applicability", support, origins, counterexamples, {}, False)
    if len(origins) < 2:
        return AgentGovernanceResult(str(candidate_type), False, "insufficient_independence", support, origins, counterexamples, dict(applicability), False)
    if counterexamples:
        return AgentGovernanceResult(str(candidate_type), False, "counterexamples_unresolved", support, origins, counterexamples, dict(applicability), False)
    if len(support) < 2:
        return AgentGovernanceResult(str(candidate_type), False, "insufficient_recurrence", support, origins, counterexamples, dict(applicability), False)
    return AgentGovernanceResult(str(candidate_type), True, "governance_passed", support, origins, counterexamples, dict(applicability), False)
