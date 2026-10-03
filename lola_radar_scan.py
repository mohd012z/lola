"""Radar scan — /360 as a cheap two-pass system.

docs/superpowers/specs/new-lola-cognitive-mesh-controls.md, Module D.

/360 does NOT mean "make the answer long" and does NOT mean "inspect
everything deeply". It means: look everywhere cheaply, investigate
selectively. Pass A scores every dimension against the question;
Pass B studies only the dimensions worth studying.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

# The 360 universe: fixed dimension set, stable order. Each dimension
# carries keywords used by the cheap relevance score.
RADAR_DIMENSIONS: tuple = (
    ("architecture", ("architecture", "design", "structure", "module", "component")),
    ("code", ("code", "source", "function", "method", "algorithm", "logic", "python", "decoder")),
    ("dependencies", ("dependency", "library", "package", "import")),
    ("runtime", ("runtime", "threading", "freeze", "hang", "performance", "latency")),
    ("network", ("network", "socket", "http", "api", "connection")),
    ("storage", ("storage", "database", "file", "cache", "buffer")),
    ("state", ("state", "lifecycle", "session", "memory")),
    ("security", ("security", "permission", "auth", "boundary", "vulnerability")),
    ("tests", ("test", "coverage", "regression", "suite")),
    ("performance", ("performance", "latency", "speed", "throughput", "slow")),
    ("build", ("build", "compile", "package", "ci", "deploy")),
    ("ui", ("ui", "android", "apk", "screen", "interface")),
    ("evidence", ("log", "evidence", "observation", "trace", "error")),
)


def _tokens(value: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", str(value).lower()) if len(t) > 2}


def relevance_score(question_tokens: set, keywords: Sequence[str]) -> int:
    """Number of distinct dimension keywords present as whole words.

    Strict token equality (not substring): "auth" must not fire on
    "author", "test" must not fire on "context".
    """
    return len({kw for kw in keywords if kw in question_tokens})


@dataclass(frozen=True)
class DimensionResult:
    name: str
    relevance: str   # ACTIVE | REVIEW | LOW
    status: str      # GREEN | CYAN | YELLOW | RED | GREY


@dataclass(frozen=True)
class RadarResult:
    question: str
    dimensions: tuple


def fast_radar(
    question: str,
    *,
    known: Sequence[str] = (),
    uncertain: Sequence[str] = (),
    contradictions: Sequence[str] = (),
) -> RadarResult:
    """Pass A: score every dimension cheaply.

    relevance: ACTIVE (>=2 keyword hits), REVIEW (1 hit), LOW (0 hits)
    status: RED (contradiction) > GREEN (known) > YELLOW (uncertain)
            > CYAN (relevant but not known/uncertain) > GREY (LOW)
    """
    known_set = set(known)
    uncertain_set = set(uncertain)
    contradiction_set = set(contradictions)
    qt = _tokens(question)
    results = []
    for name, keywords in RADAR_DIMENSIONS:
        hits = relevance_score(qt, keywords)
        if hits >= 2:
            relevance = "ACTIVE"
        elif hits == 1:
            relevance = "REVIEW"
        else:
            relevance = "LOW"
        if name in contradiction_set:
            status = "RED"
        elif name in known_set:
            status = "GREEN"
        elif name in uncertain_set:
            status = "YELLOW"
        elif relevance == "LOW":
            status = "GREY"
        else:
            status = "CYAN"
        results.append(DimensionResult(name, relevance, status))
    return RadarResult(question=question, dimensions=tuple(results))


def pass_b(radar: RadarResult) -> tuple:
    """Pass B: the dimensions worth investigating.

    A dimension is worth a deep pass if its status is CYAN (relevant but
    unflagged), YELLOW (flagged uncertain), or RED (flagged contradiction).
    GREEN is already understood and GREY is irrelevant, so both are skipped.
    That is "360 degree coverage without 360 degree waste": the cheap
    status assignment is what does the pruning, so an explicitly flagged
    dimension still gets investigated even when the question never used its
    keywords.
    """
    return tuple(d.name for d in radar.dimensions
                 if d.status in ("CYAN", "YELLOW", "RED"))
