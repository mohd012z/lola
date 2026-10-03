"""Defensive near-duplicate clustering and family evidence.

Outputs are observations only. This module intentionally has no ALLOW/REVIEW/BLOCK
authority; GuardPipeline remains the sole policy decision boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .corpus_adapter import CorpusRecord, normalize


@dataclass(frozen=True)
class FamilyEvidence:
    name: str
    confidence: float
    signals: tuple[str, ...]


@dataclass(frozen=True)
class CorpusCluster:
    members: tuple[CorpusRecord, ...]
    similarity: float
    family: FamilyEvidence


def _tokens(text: str) -> set[str]:
    text = normalize(text).lower()
    words = re.findall(r"[a-z0-9_]+", text)
    # Small stemming step improves resilience to harmless singular/plural edits.
    return {word[:-1] if len(word) > 4 and word.endswith("s") else word for word in words}


def token_similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def classify_family(text: str) -> FamilyEvidence:
    lowered = normalize(text).lower()
    signals: list[str] = []
    families: list[str] = []

    hierarchy = ("ignore system", "ignore the system", "override system", "system rules", "system instruction")
    hidden = ("hidden instruction", "hidden prompt", "reveal instruction", "reveal prompt")
    role = ("pretend you are", "act as unrestricted", "new role")
    obfuscation = ("base64", "decode this", "encoded instruction")
    safety = ("disable safety", "bypass safety", "evade guardrail")

    for name, phrases in (
        ("hierarchy_conflict", hierarchy),
        ("hidden_instruction", hidden),
        ("role_manipulation", role),
        ("obfuscation", obfuscation),
        ("safety_evasion", safety),
    ):
        hits = [phrase for phrase in phrases if phrase in lowered]
        if hits:
            families.append(name)
            signals.extend(f"{name}:{phrase}" for phrase in hits)

    if not families:
        return FamilyEvidence("unclassified", 0.0, ())
    name = families[0] if len(families) == 1 else "mixed"
    confidence = min(1.0, round(0.55 + 0.1 * len(set(signals)), 4))
    return FamilyEvidence(name, confidence, tuple(sorted(set(signals))))


def cluster_records(records: Iterable[CorpusRecord], threshold: float = 0.75) -> list[CorpusCluster]:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    groups: list[list[CorpusRecord]] = []
    similarities: list[float] = []

    for record in records:
        best_index = -1
        best_score = -1.0
        for index, group in enumerate(groups):
            score = max(token_similarity(record.text, member.text) for member in group)
            if score >= threshold and score > best_score:
                best_index, best_score = index, score
        if best_index < 0:
            groups.append([record])
            similarities.append(1.0)
        else:
            groups[best_index].append(record)
            similarities[best_index] = min(similarities[best_index], best_score)

    output: list[CorpusCluster] = []
    for group, similarity in zip(groups, similarities):
        family_candidates = [classify_family(member.text) for member in group]
        family = max(family_candidates, key=lambda item: item.confidence)
        output.append(CorpusCluster(tuple(group), round(similarity, 4), family))
    return output
