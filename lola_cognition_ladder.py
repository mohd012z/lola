"""Cognition ladder — Tiny-to-Beast made mechanical.

docs/superpowers/specs/new-lola-discovery-learning.md, Module A.

The kernel never asks "which model do we use?". It asks "what is the
smallest capability capable of closing this specific gap?". Every gap
enters a ladder whose cost (in LLM usage) strictly increases, and the
lowest level that can close the gap wins. L0-L4 make ZERO LLM calls;
model levels (L5/L6/L7) are only reached when no internal path closes
the gap and the required tier is actually available.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class LadderLevel:
    name: str
    llm: str  # none | local | stronger | external
    description: str


# L0-L4 = zero-LLM internal cognition; L5/L6 = local models; L7 = external; L8 = human.
LEVELS = (
    LadderLevel("L0", "none", "deterministic computation / lookup"),
    LadderLevel("L1", "none", "retrieved governed knowledge"),
    LadderLevel("L2", "none", "retrieved verified experience / transfer"),
    LadderLevel("L3", "none", "internal derivation from known facts"),
    LadderLevel("L4", "none", "novel synthesis (novelty engine)"),
    LadderLevel("L5", "local", "small local model"),
    LadderLevel("L6", "stronger", "larger local model"),
    LadderLevel("L7", "external", "external intelligence (remote LLM / docs / repos)"),
    LadderLevel("L8", "none", "human escalation"),
)
_LEVEL_BY_NAME = {lvl.name: lvl for lvl in LEVELS}

# tier name -> (level name, llm class); local tiers ordered cheapest-first.
_TIER_LOCAL = (("tiny_local", "L5"), ("large_local", "L6"))
_TIER_REMOTE = (("remote_optional", "L7"),)


@dataclass(frozen=True)
class LadderDecision:
    level: str
    llm_class: str
    reason: str
    provider: str | None = None

    @property
    def uses_llm(self) -> bool:
        return self.llm_class in ("local", "stronger", "external")


def smallest_capability(
    *,
    gap_type: str,
    knowledge_available: bool = False,
    experience_available: bool = False,
    derivable: bool = False,
    novel_candidate: bool = False,
    tiers: Mapping[str, object] | set | None = None,
    network_available: bool = False,
    human_required: bool = False,
) -> LadderDecision:
    """Return the cheapest ladder level that can close the gap.

    Deterministic and inspectable: `reason` explains the choice, `provider`
    names the concrete tier for model levels. `level` is one of "L0".."L8"
    or "ESCALATE" (the only remaining route was a remote tier blocked by
    the network — stall, do not silently drop to a local floor that is not
    registered).
    """
    tiers = set(tiers or ())

    if human_required:
        return LadderDecision("L8", "none", "human_required")

    # Cheapest useful internal cognition first — always zero LLM calls.
    if knowledge_available:
        return LadderDecision("L1", "none", "verified_knowledge_available")
    if experience_available:
        return LadderDecision("L2", "none", "verified_experience_available")
    if derivable:
        return LadderDecision("L3", "none", "internal_derivation_available")
    if novel_candidate:
        return LadderDecision("L4", "none", "novel_synthesis_available")

    # Model fabric, cheapest tier first.
    for tier, level in _TIER_LOCAL:
        if tier in tiers:
            return LadderDecision(level, _LEVEL_BY_NAME[level].llm,
                                  "local_tier_available", provider=tier)

    remote = [tier for tier, _ in _TIER_REMOTE if tier in tiers]
    if remote:
        if not network_available:
            return LadderDecision("ESCALATE", "none",
                                  "remote_tier_requires_unavailable_network")
        tier = remote[0]
        return LadderDecision("L7", "external", "remote_tier_available", provider=tier)

    # Floor. A capability gap with no capability at all can only be closed
    # by a human; any other gap still gets a deterministic attempt.
    if gap_type == "CAPABILITY" and not tiers:
        return LadderDecision("L8", "none", "no_capability_available")
    return LadderDecision("L0", "none", "deterministic_floor")
