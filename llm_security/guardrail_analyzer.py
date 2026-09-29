"""Defensive prompt-risk analysis for Lola.

This module identifies structural indicators associated with prompt injection and
jailbreak attempts. It deliberately does not generate, optimize, or replay
jailbreak payloads.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Iterable


@dataclass(frozen=True)
class Signal:
    name: str
    score: float
    evidence: str


@dataclass(frozen=True)
class Analysis:
    fingerprint: str
    risk_score: float
    decision: str
    signals: tuple[Signal, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


# Structural indicators only. Keep the detector defensive and explainable.
_PATTERNS: dict[str, tuple[re.Pattern[str], float]] = {
    "instruction_override": (
        re.compile(r"\b(ignore|disregard|override|bypass)\b.{0,48}\b(instruction|rule|policy|guardrail|system)\b", re.I | re.S),
        0.30,
    ),
    "role_manipulation": (
        re.compile(r"\b(pretend|roleplay|act as|you are now|new persona)\b", re.I),
        0.16,
    ),
    "hidden_instruction_request": (
        re.compile(r"\b(reveal|print|show|repeat|expose)\b.{0,40}\b(system prompt|hidden instruction|developer message)\b", re.I | re.S),
        0.28,
    ),
    "safety_evasion_language": (
        re.compile(r"\b(without restrictions|no restrictions|disable safety|remove safeguards|uncensored)\b", re.I),
        0.30,
    ),
    "encoding_pressure": (
        re.compile(r"\b(base64|rot13|hex(?:adecimal)?|encode|decode|obfuscat)\b", re.I),
        0.10,
    ),
}


def _normalise(text: str) -> str:
    return " ".join(text.replace("\x00", " ").split())


def analyse(text: str) -> Analysis:
    clean = _normalise(text)
    fingerprint = hashlib.sha256(clean.encode("utf-8")).hexdigest()
    found: list[Signal] = []
    total = 0.0

    for name, (pattern, weight) in _PATTERNS.items():
        match = pattern.search(clean)
        if match:
            total += weight
            # Record signal class, not sensitive/full prompt content.
            found.append(Signal(name, weight, f"matched structural indicator at {match.start()}:{match.end()}"))

    # Multiple independent indicators increase confidence without allowing one
    # weak keyword to dominate the result.
    if len(found) >= 3:
        total += 0.12
    elif len(found) == 2:
        total += 0.05

    score = round(min(total, 1.0), 3)
    if score >= 0.65:
        decision = "BLOCK"
    elif score >= 0.30:
        decision = "REVIEW"
    else:
        decision = "ALLOW"

    return Analysis(fingerprint, score, decision, tuple(found))


def analyse_many(prompts: Iterable[str]) -> list[Analysis]:
    return [analyse(prompt) for prompt in prompts]
