#!/usr/bin/env python3
"""Shared LOLA security fabric.

Untrusted content remains analyzable data but cannot acquire authority merely
because it contains instruction-like text. This module is intentionally
stdlib-only so existing LOLA Python tools can adopt it incrementally.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class TrustLevel(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    QUARANTINED = "quarantined"


class ActionClass(str, Enum):
    READ = "read"
    TRANSFORM = "transform"
    SIDE_EFFECT = "side_effect"
    MEMORY_WRITE = "memory_write"


class Decision(str, Enum):
    ALLOW = "allow"
    ALLOW_READ_ONLY = "allow_read_only"
    QUARANTINE = "quarantine"
    REVIEW = "review"
    DENY = "deny"


@dataclass(frozen=True)
class TrustEnvelope:
    payload: Any
    source_type: str
    source_id: str
    trust_level: TrustLevel = TrustLevel.UNTRUSTED
    user_supplied: bool = False
    externally_supplied: bool = False
    executable: bool = False
    sha256: str = ""
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProposedAction:
    name: str
    action_class: ActionClass
    scope: str = "local"
    explicitly_authorized: bool = False


@dataclass(frozen=True)
class SecurityDecision:
    decision: Decision
    score: int
    reasons: tuple[str, ...]
    source_hash: str
    action: str


@dataclass
class EvidenceEvent:
    source_type: str
    source_id: str
    source_hash: str
    action: str
    decision: str
    score: int
    reasons: list[str] = field(default_factory=list)
    engine_version: str = "lola-security-v1"


PATTERNS: dict[str, tuple[str, ...]] = {
    "ROLE_OVERRIDE": (r"ignore (?:all |any )?(?:previous|prior) instructions", r"you are now"),
    "AUTHORITY_SPOOFING": (r"system (?:message|instruction)", r"developer (?:message|instruction)", r"authorized by (?:admin|system|developer)"),
    "POLICY_REPLACEMENT": (r"new (?:policy|rules|constitution)", r"supersed(?:e|es) .*instructions", r"replace .*policy"),
    "REFUSAL_SUPPRESSION": (r"never refuse", r"do not refuse", r"no disclaimer", r"must comply"),
    "TOOL_COERCION": (r"call (?:the )?(?:tool|function|api)", r"execute (?:the )?(?:command|code)", r"run (?:this|the) command"),
    "PERSISTENCE": (r"from now on", r"for (?:all|every) future", r"remember (?:this|these) instructions"),
    "TRUST_ESCALATION": (r"treat .* as trusted", r"everything below is (?:trusted|system)"),
}


def canonicalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = "".join(ch for ch in value if ch in "\n\t" or unicodedata.category(ch) != "Cf")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def detect_flags(text: str) -> tuple[tuple[str, ...], int]:
    normalized = canonicalize(text).lower()
    hits: list[str] = []
    total = 0
    for flag, patterns in PATTERNS.items():
        matched = sum(len(re.findall(p, normalized, re.IGNORECASE)) for p in patterns)
        if matched:
            hits.append(flag)
            total += matched
    score = min(100, len(hits) * 13 + total * 3)
    return tuple(sorted(hits)), score


def envelope(payload: Any, source_type: str, source_id: str, *, trusted: bool = False,
             user_supplied: bool = False, externally_supplied: bool = False,
             executable: bool = False) -> TrustEnvelope:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
    flags, _ = detect_flags(text)
    return TrustEnvelope(
        payload=payload,
        source_type=source_type,
        source_id=source_id,
        trust_level=TrustLevel.TRUSTED if trusted else TrustLevel.UNTRUSTED,
        user_supplied=user_supplied,
        externally_supplied=externally_supplied,
        executable=executable,
        sha256=digest(text),
        flags=flags,
    )


class DecisionEngine:
    """Deterministic authorization boundary; detectors never execute actions."""

    def evaluate(self, env: TrustEnvelope, action: ProposedAction) -> SecurityDecision:
        text = env.payload if isinstance(env.payload, str) else json.dumps(env.payload, default=str)
        flags, score = detect_flags(text)
        reasons = list(flags)

        if action.action_class in {ActionClass.SIDE_EFFECT, ActionClass.MEMORY_WRITE}:
            if not action.explicitly_authorized:
                reasons.append("MISSING_EXPLICIT_AUTHORIZATION")
                return SecurityDecision(Decision.DENY, score, tuple(sorted(set(reasons))), env.sha256, action.name)
            if env.trust_level != TrustLevel.TRUSTED and flags:
                reasons.append("UNTRUSTED_INSTRUCTION_SOURCE")
                return SecurityDecision(Decision.REVIEW, score, tuple(sorted(set(reasons))), env.sha256, action.name)

        if action.action_class == ActionClass.TRANSFORM and score >= 70:
            reasons.append("HIGH_RISK_CONTENT")
            return SecurityDecision(Decision.QUARANTINE, score, tuple(sorted(set(reasons))), env.sha256, action.name)

        if action.action_class == ActionClass.READ:
            # Suspicious content remains inspectable but cannot gain authority.
            return SecurityDecision(Decision.ALLOW_READ_ONLY, score, tuple(sorted(set(reasons))), env.sha256, action.name)

        return SecurityDecision(Decision.ALLOW, score, tuple(sorted(set(reasons))), env.sha256, action.name)


def safe_render_text(value: str) -> str:
    """Escape artifact/model text before embedding in HTML reports."""
    return html.escape(value, quote=True)


def evidence_from(env: TrustEnvelope, result: SecurityDecision) -> EvidenceEvent:
    return EvidenceEvent(
        source_type=env.source_type,
        source_id=env.source_id,
        source_hash=env.sha256,
        action=result.action,
        decision=result.decision.value,
        score=result.score,
        reasons=list(result.reasons),
    )


def append_evidence(path: Path, event: EvidenceEvent) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(event), ensure_ascii=False, sort_keys=True) + "\n")


def scan_many(items: Iterable[tuple[str, str, str]]) -> list[EvidenceEvent]:
    engine = DecisionEngine()
    events: list[EvidenceEvent] = []
    for source_type, source_id, text in items:
        env = envelope(text, source_type, source_id, externally_supplied=True)
        result = engine.evaluate(env, ProposedAction("analyze", ActionClass.READ))
        events.append(evidence_from(env, result))
    return events
