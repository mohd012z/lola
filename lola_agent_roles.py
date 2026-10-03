"""Agent roles — specialization emerges from the question.

docs/superpowers/specs/agent-roles-and-observe-v1.md, Module N.

The kernel does NOT run a permanent pool of agents. It derives the
cognitive roles the question actually needs. Seven roles, fixed
lifecycle order; VERIFIER is always present (evidence-first: every
claim is checked against an observation) and SYNTHESIZER only when
there is genuinely more than one stream to integrate.
"""
from __future__ import annotations

from typing import Sequence

# The seven cognitive roles, in lifecycle order.
LIFECYCLE = (
    "EXPLORER",     # find possibilities
    "ANALYST",      # build the mechanism
    "RESEARCHER",   # find external evidence
    "SKEPTIC",      # attack the assumptions
    "EXPERIMENTER", # design the tests
    "VERIFIER",     # check claims against observations
    "SYNTHESIZER",  # integrate results
)

COGNITIVE_ROLES = LIFECYCLE

# Canned template per question type (from #47's planner). All end in
# VERIFIER + SYNTHESIZER.
_TYPE_TEMPLATES = {
    "TROUBLESHOOTING": (
        "EXPLORER", "ANALYST", "SKEPTIC", "EXPERIMENTER", "VERIFIER",
        "SYNTHESIZER",
    ),
    "RESEARCH": (
        "EXPLORER", "RESEARCHER", "ANALYST", "SKEPTIC", "VERIFIER",
        "SYNTHESIZER",
    ),
    "IMPLEMENTATION": (
        "EXPLORER", "ANALYST", "EXPERIMENTER", "VERIFIER", "SYNTHESIZER",
    ),
    "GENERIC": (
        "EXPLORER", "ANALYST", "VERIFIER", "SYNTHESIZER",
    ),
}

_INDEX = {role: i for i, role in enumerate(LIFECYCLE)}


def _ordered(roles) -> tuple:
    return tuple(sorted(set(roles), key=lambda r: _INDEX[r]))


def role_for_question_type(question_type: str) -> tuple:
    if question_type not in _TYPE_TEMPLATES:
        raise ValueError(f"unknown question type: {question_type}")
    return _TYPE_TEMPLATES[question_type]


def _classify(question: str) -> str:
    # reuse #47's deterministic classifier
    from lola_answer_planner import plan_answer
    return plan_answer(question).question_type


def derive_roles(question: str, gap: Sequence[str] = ()) -> tuple:
    """Specialization that emerges from the question + its open gaps.

    EXPLORER and VERIFIER are always present. The type template supplies
    the mechanism/research/skeptic/experiment roles. SYNTHESIZER is only
    kept when there is more than one stream to integrate: >= 2 open gaps,
    or a RESEARCH question with any gap. Otherwise a single known fact
    does not need a synthesizer — minimal, not maximal.
    """
    qtype = _classify(question)
    base = set(role_for_question_type(qtype))
    # EXPLORER always first; VERIFIER always present.
    base.add("EXPLORER")
    base.add("VERIFIER")
    needs_synthesis = (
        len(list(gap)) >= 2 or (qtype == "RESEARCH" and len(list(gap)) >= 1)
    )
    if not needs_synthesis:
        base.discard("SYNTHESIZER")
    return _ordered(base)
