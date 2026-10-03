"""Fast triage — the cheap first pass before any deep cognition.

docs/superpowers/specs/new-lola-runtime-loop-v1.md, Module H.

"Don't start deep." Within the first cheap pass, decide:
  1. ANSWER  — the question is already answered by verified state;
  2. INSPECT — deterministic inspection (logs/files/diff/build) closes
     the gap;
  3. MAP     — build the complexity/radar map and continue.

Triage NEVER justifies external access by itself. That is the
research gate's decision, later, only if internal reasoning is
exhausted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


def _tokens(value: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", str(value).lower()) if len(t) > 2}


_INSPECT_KEYWORDS = (
    "file", "log", "diff", "test", "build", "status", "dependency",
    "schema", "compile", "version", "size", "count",
)


@dataclass(frozen=True)
class Triage:
    route: str            # ANSWER | INSPECT | MAP
    why: str
    external_justified: bool   # always False at triage time
    match: str = ""       # the verified key / inspectable that decided


def _verified_match(question: str, verified_state: Mapping[str, str]) -> str:
    """A verified entry answers the question when the question contains
    at least 2 of the entry's terms (deterministic token overlap)."""
    qt = _tokens(question)
    best_key = ""
    best_hits = 1
    for key, _value in verified_state.items():
        kt = _tokens(key)
        hits = len(qt & kt)
        if hits >= 2 and hits > best_hits:
            best_hits = hits
            best_key = key
    return best_key


def fast_triage(
    question: str,
    *,
    verified_state: Mapping[str, str] | None = None,
    inspectable: Sequence[str] = (),
) -> Triage:
    verified_state = verified_state or {}
    key = _verified_match(question, verified_state)
    if key:
        return Triage("ANSWER", f"answered from verified state: {key}",
                      False, match=key)
    qt = _tokens(question)
    hit = next((kw for kw in _INSPECT_KEYWORDS if kw in qt), "")
    if hit:
        return Triage("INSPECT",
                      f"deterministic inspection closes the gap: {hit}",
                      False, match=hit)
    return Triage("MAP", "complexity/uncertainty map required", False)
