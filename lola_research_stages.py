"""Staged research — local knowledge first, AI sources last.

docs/superpowers/specs/new-lola-runtime-loop-v1.md, Module I.

Explicitly prohibited:
    QUESTION -> Google/GPT/etc. -> copy findings

New LOLA research is staged: local knowledge -> evidence inventory ->
known/unknown -> internal hypotheses -> FREEZE -> research plan ->
source selection. Source order is trust, not convenience:
    PRIMARY (code/runtime/docs/spec/raw data)
      -> SECONDARY (technical analysis)
        -> COMMUNITY (issues/forums/experience reports)
          -> AI (Qwen/GPT/Claude/Gemini) — last; useful for hypothesis
             expansion and critique, and agreement among AI models
             counts as ZERO independent evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

SOURCE_RANK = {
    "primary": 0,
    "secondary": 1,
    "community": 2,
    "ai": 3,
}

# Known source -> class. Used to validate claimed classes.
_SOURCE_CLASS = {
    "code": "primary", "runtime": "primary", "docs": "primary",
    "spec": "primary", "raw_data": "primary", "official_docs": "primary",
    "analysis": "secondary", "research_paper": "secondary",
    "community": "community", "issues": "community", "forums": "community",
    "qwen": "ai", "gpt": "ai", "claude": "ai", "gemini": "ai", "ai": "ai",
}

STAGES = (
    "local_knowledge",
    "evidence_inventory",
    "known_unknown",
    "internal_hypotheses",
    "freeze_hypotheses",
    "research_plan",
    "source_selection",
)


def source_rank(name: str) -> int:
    name = name.strip().lower()
    if name in SOURCE_RANK:
        return SOURCE_RANK[name]
    if name in _SOURCE_CLASS:
        return SOURCE_RANK[_SOURCE_CLASS[name]]
    return 99  # unknown sources rank below everything, not above


@dataclass(frozen=True)
class Query:
    root: str
    text: str
    parent: str = ""


@dataclass(frozen=True)
class ResearchPlan:
    stages: tuple
    queries: tuple
    sources: tuple                 # tuple[(name, claimed_class)]
    ai_consulted: tuple
    evidence_contributions_from_ai: int  # always 0
    frozen: bool = True


def _check_source(name: str, claimed: str) -> str:
    claimed = claimed.strip().lower()
    actual = _SOURCE_CLASS.get(name.strip().lower(), "community")
    if actual != claimed:
        raise ValueError(
            f"source class mismatch: {name!r} is {actual}, claimed {claimed}"
        )
    return claimed


def build_research_plan(
    gap: str,
    *,
    local_known: Sequence[str] = (),
    local_unknown: Sequence[str] = (),
    sources: Sequence[tuple] = (),
    ai_agreement: Sequence[str] = (),
    external_gaps: Sequence[str] = (),
    frozen: bool = True,
) -> ResearchPlan:
    if not frozen:
        raise ValueError("hypotheses must be FROZEN before external research")
    queries = [Query(root=gap, text=f"root: {gap}")]
    for g in external_gaps:
        queries.append(Query(root=gap, text=f"gap: {g}", parent=gap))
    checked = tuple((n, _check_source(n, c)) for n, c in sources)
    return ResearchPlan(
        stages=STAGES,
        queries=tuple(queries),
        sources=checked,
        ai_consulted=tuple(ai_agreement),
        evidence_contributions_from_ai=0,
        frozen=True,
    )
