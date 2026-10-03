"""Answer planner — pick the answer's sections by question type.

docs/superpowers/specs/answer-planner-and-loop-smoke.md, Module L.

Before writing the answer, decide which sections it needs. The plan is
a pure function of the question text: deterministic keyword
classification, fixed tie-break order, and a fixed section template per
type. No LLM, no prose rendering — the planner only decides WHICH
sections; writing them is the answer stage's job.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

# Whole-token keyword sets per question type.
_TROUBLESHOOTING = (
    "why", "error", "fail", "failed", "failure", "freeze", "frozen",
    "crash", "crashes", "bug", "broken", "hang", "hung", "not",
    "working", "issue", "problem", "cause", "causes",
)
_RESEARCH = (
    "research", "study", "survey", "compare", "compared", "evaluate",
    "analyze", "analyse", "investigate", "evidence", "which", "best",
    "options",
)
_IMPLEMENTATION = (
    "implement", "build", "create", "add", "change", "modify", "write",
    "develop", "make", "deploy", "integrate", "refactor",
)

# Fixed priority for tie-breaking (and the fallback for zero hits).
_PRIORITY = ("TROUBLESHOOTING", "RESEARCH", "IMPLEMENTATION")

_TEMPLATES = {
    "TROUBLESHOOTING": (
        "Finding", "Evidence", "Root cause", "Fix", "Verification",
        "Unknowns",
    ),
    "RESEARCH": (
        "Question", "Known evidence", "Competing explanations",
        "Findings", "Limitations", "Conclusion",
    ),
    "IMPLEMENTATION": (
        "Target", "Change", "Dependencies", "Implementation", "Tests",
        "Regression", "Result",
    ),
    "GENERIC": (
        "Summary", "Evidence", "Reasoning", "Result", "Unknowns",
    ),
}

_KEYWORDS = {
    "TROUBLESHOOTING": _TROUBLESHOOTING,
    "RESEARCH": _RESEARCH,
    "IMPLEMENTATION": _IMPLEMENTATION,
}


def _tokens(value: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", str(value).lower()) if len(t) > 2}


@dataclass(frozen=True)
class AnswerPlan:
    question_type: str
    reason: tuple      # winning tokens (diagnostic)
    sections: tuple    # ordered, all required


def plan_answer(question: str) -> AnswerPlan:
    qt = _tokens(question)
    scores = {t: len(qt & set(_KEYWORDS[t])) for t in _PRIORITY}
    best = max(scores.values())
    if best == 0:
        return AnswerPlan("GENERIC", (), _TEMPLATES["GENERIC"])
    winners = [t for t in _PRIORITY if scores[t] == best]
    # fixed priority wins ties: first in _PRIORITY
    chosen = winners[0]
    hit_tokens = tuple(sorted(qt & set(_KEYWORDS[chosen])))
    return AnswerPlan(chosen, hit_tokens, _TEMPLATES[chosen])


def planned_sections(questions: Sequence[str]) -> tuple:
    return tuple(plan_answer(q).sections for q in questions)
