"""Novelty Engine + Idea Genome — independent thinking before external sources.

docs/superpowers/specs/new-lola-discovery-learning.md, Module B.

Anam's requirement: "LOLA must have the capability to create a new idea —
novel — before asking external sources." This module is the
NO_EXTERNAL_HINT protected phase: a structured, *testable* idea is produced
and frozen before any external research is permitted.

The engine here is a deterministic **structure + scoring** harness. It does
not generate semantic content (that is the L5+ model's job when a model
level is actually selected by the cognition ladder); it guarantees that any
idea LOLA keeps is an executable hypothesis with a falsification condition,
that "novel" is a strict level and not random text, and that independence
against external sources is classified honestly (NO_MATCH_FOUND is never
WORLD_FIRST).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class IdeaGenome:
    """A structured, testable idea — not prose."""

    problem: str
    observations: tuple
    known_facts: tuple
    assumptions: tuple
    primitives: tuple
    abstraction: str
    mechanism: str
    causal_chain: tuple
    predictions: tuple
    counterpredictions: tuple
    experiment: str
    falsification_condition: str
    provenance: tuple
    status: str = "UNTESTED"
    idea_id: str = ""

    def __post_init__(self):
        if not self.idea_id:
            digest = hashlib.sha256(
                "|".join((self.problem, self.mechanism, self.falsification_condition)).encode()
            ).hexdigest()[:16]
            object.__setattr__(self, "idea_id", f"idea-{digest}")


def _as_tuple(value: Sequence | None) -> tuple:
    return tuple(value or ())


def build_idea_genome(
    *,
    problem: str,
    observations=(),
    known_facts=(),
    assumptions=(),
    primitives=(),
    abstraction: str = "",
    mechanism: str,
    causal_chain=(),
    predictions=(),
    counterpredictions=(),
    experiment: str = "",
    falsification_condition: str,
    provenance=(),
) -> IdeaGenome:
    """Validate + construct an IdeaGenome.

    An idea with no mechanism, no prediction, or no falsification
    condition is rejected — untestable ideas are not stored (this is what
    stops "generate random text and call it innovation").
    """
    if not str(problem).strip():
        raise ValueError("problem is required")
    if not str(mechanism).strip():
        raise ValueError("mechanism is required")
    preds = _as_tuple(predictions)
    if not preds:
        raise ValueError("at least one prediction is required")
    if not str(falsification_condition).strip():
        raise ValueError("falsification_condition is required")
    return IdeaGenome(
        problem=str(problem),
        observations=_as_tuple(observations),
        known_facts=_as_tuple(known_facts),
        assumptions=_as_tuple(assumptions),
        primitives=_as_tuple(primitives),
        abstraction=str(abstraction),
        mechanism=str(mechanism),
        causal_chain=_as_tuple(causal_chain),
        predictions=preds,
        counterpredictions=_as_tuple(counterpredictions),
        experiment=str(experiment),
        falsification_condition=str(falsification_condition),
        provenance=_as_tuple(provenance),
    )


def novelty_level(
    *,
    primitives_known: bool = False,
    cross_domain: bool = False,
    new_mechanism: bool = False,
    has_testable_prediction: bool = False,
) -> str:
    """Strict novelty level so "novel" is not a free claim.

    N1 compositional (known A + known B -> unseen C), N2 structural
    (pattern transferred across domains), N3 mechanistic (previously
    unstated causal mechanism). NONE when the idea is not testable.
    """
    if not has_testable_prediction:
        return "NONE"
    if new_mechanism:
        return "N3"
    if cross_domain:
        return "N2"
    if primitives_known:
        return "N1"
    return "NONE"


def freeze_idea(idea: IdeaGenome) -> dict:
    """Lock the idea BEFORE any external search.

    Prevents post-hoc contamination: the frozen snapshot (id, timestamp,
    evidence, derivation, predictions) is what independence is judged
    against. Returns a new dict; the genome is not mutated.
    """
    return {
        "idea_id": idea.idea_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "problem": idea.problem,
        "evidence": list(idea.provenance),
        "derivation": {
            "abstraction": idea.abstraction,
            "mechanism": idea.mechanism,
            "causal_chain": list(idea.causal_chain),
        },
        "predictions": list(idea.predictions),
        "counterpredictions": list(idea.counterpredictions),
        "falsification_condition": idea.falsification_condition,
    }


def _tokens(value: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", str(value).lower()) if len(t) > 2}


def _overlap_ratio(a: set, b: set) -> float:
    if not a:
        return 0.0
    return len(a & b) / len(a)


def classify_independence(
    frozen: Mapping[str, Any],
    external_matches: Sequence[str],
    novel_mechanism: bool = False,  # accepted for API symmetry; not used in the overlap rule
) -> str:
    """Classify a frozen idea against external research findings.

    Deterministic token-overlap rule on the frozen mechanism:
      >= 0.6 overlap  -> KNOWN (the mechanism is documented)
      > 0 overlap     -> INDEPENDENT_REDISCOVERY (same space, we derived it
                         without the source)
      no mechanism overlap but the external set is non-empty
                        -> NOVEL_COMBINATION (nothing overlaps; still NOT
                           world-first)
      no matches at all -> NO_MATCH_FOUND

    The hard invariant: NO_MATCH_FOUND is returned as-is — it must NEVER be
    upgraded to "world first" (absence of evidence is not evidence of
    novelty).
    """
    matches = [str(m) for m in external_matches if str(m).strip()]
    if not matches:
        return "NO_MATCH_FOUND"
    derivation = frozen.get("derivation", {}) or {}
    mech_tokens = _tokens(derivation.get("mechanism", ""))
    best = 0.0
    for m in matches:
        best = max(best, _overlap_ratio(mech_tokens, _tokens(m)))
    if best >= 0.6:
        return "KNOWN"
    if best > 0:
        return "INDEPENDENT_REDISCOVERY"
    return "NOVEL_COMBINATION"


# Diverge -> converge: score each candidate, never trust order/confidence.
_AXES = (
    "evidence_coverage",
    "causal_consistency",
    "assumption_burden",
    "contradictions",
    "testability",
    "falsifiability",
    "information_gain",
    "experimental_cost",
)


def _score(idea: IdeaGenome, evidence: Mapping[str, Any]) -> int:
    score = 0
    score += min(len(idea.observations) + len(idea.known_facts), 4)          # evidence coverage
    score += min(len(idea.causal_chain), 4)                                  # causal consistency
    score -= len(idea.assumptions)                                           # assumption burden
    score += 2 if idea.falsification_condition else -4                       # falsifiability
    score += 2 if idea.predictions else -4                                   # testability
    score += 1 if idea.counterpredictions else 0                             # information gain
    score += 0 if idea.experiment else -2                                    # experimental cost
    return score


def challenge_ideas(ideas: Sequence[IdeaGenome], evidence: Mapping[str, Any]) -> dict:
    """Return {idea_id: verdict} for a divergent set.

    Verdicts: KNOWN_COUNTEREXAMPLE / TESTABLE / INSUFFICIENT. Selection is
    by scored merit (ties keep the higher score, never the input order); a
    counterexample named for the idea's mechanism is always rejected.
    """
    counter = set(str(x) for x in (evidence.get("known_counterexample_for") or ()))
    out: dict[str, str] = {}
    for idea in ideas:
        if idea.mechanism in counter or any(c in idea.causal_chain for c in counter):
            out[idea.idea_id] = "KNOWN_COUNTEREXAMPLE"
            continue
        s = _score(idea, evidence)
        if s >= 2 and idea.falsification_condition and idea.predictions:
            out[idea.idea_id] = "TESTABLE"
        else:
            out[idea.idea_id] = "INSUFFICIENT"
    return out
