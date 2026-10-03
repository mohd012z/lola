"""Deterministic repeated-agent experience analysis.

Recurrence is descriptive evidence about patterns, never verification by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping, Tuple


def _normalize(value: Any):
    if isinstance(value, Mapping):
        return {str(k): _normalize(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple, set)):
        normalized = [_normalize(v) for v in value]
        return sorted(normalized, key=lambda v: json.dumps(v, sort_keys=True, separators=(",", ":")))
    return value


def context_fingerprint(context: Mapping[str, Any]) -> str:
    payload = json.dumps(_normalize(context), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RepeatedAgentPattern:
    context_fingerprint: str
    pattern_type: str
    episode_ids: Tuple[str, ...]
    episode_count: int
    effective_independent_origins: int
    independent_origin_domains: Tuple[str, ...]
    supporting_episode_ids: Tuple[str, ...]
    contradicting_episode_ids: Tuple[str, ...]


def _classify(group):
    if group and all(bool(e.get("echo")) for e in group):
        return "ECHO_PATTERN"
    if group and all(bool(e.get("recovered")) for e in group):
        return "RECOVERY_PATTERN"
    outcomes = [str(e.get("outcome", "")) for e in group]
    if outcomes and all(o in {"FAILED", "FALSIFIED"} for o in outcomes):
        return "FAILURE_PATTERN"
    if outcomes and all(o == "VERIFIED" for o in outcomes):
        return "SUCCESS_PATTERN"
    if any(bool(e.get("stagnated")) for e in group):
        return "STAGNATION_PATTERN"
    return "CONDITIONAL_PATTERN"


def analyze_repeated_agent_episodes(episodes: Iterable[Mapping[str, Any]]):
    groups = {}
    for episode in episodes:
        fp = context_fingerprint(episode.get("context") or {})
        groups.setdefault(fp, []).append(episode)

    patterns = []
    for fp in sorted(groups):
        group = sorted(groups[fp], key=lambda e: str(e.get("episode_id", "")))
        origins = sorted({str(origin) for e in group for origin in (e.get("origin_domains") or ()) if origin})
        ptype = _classify(group)
        supporting = tuple(str(e.get("episode_id", "")) for e in group if str(e.get("outcome", "")) == "VERIFIED")
        contradicting = tuple(str(e.get("episode_id", "")) for e in group if str(e.get("outcome", "")) in {"FAILED", "FALSIFIED"})
        patterns.append(RepeatedAgentPattern(fp, ptype, tuple(str(e.get("episode_id", "")) for e in group), len(group), len(origins), tuple(origins), supporting, contradicting))
    return tuple(patterns)
