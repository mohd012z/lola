"""Deterministic preprocessing of episodic experience for governed abstraction."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping, Any, Tuple
from lola_repeated_episode import RepeatedAgentPattern, analyze_repeated_agent_episodes


@dataclass(frozen=True)
class CompiledExperience:
    input_episode_count: int
    unique_episode_count: int
    effective_independent_origins: int
    independent_origin_domains: Tuple[str, ...]
    counterexample_episode_ids: Tuple[str, ...]
    patterns: Tuple[RepeatedAgentPattern, ...]
    status: str = "ANALYZED"


def compile_experience(episodes: Iterable[Mapping[str, Any]]) -> CompiledExperience:
    incoming = list(episodes)
    unique = {}
    for episode in incoming:
        eid = str(episode.get("episode_id", ""))
        key = eid or repr(sorted((episode.get("context") or {}).items()))
        if key not in unique:
            unique[key] = dict(episode)
    ordered = tuple(sorted(unique.values(), key=lambda e: str(e.get("episode_id", ""))))
    origins = tuple(sorted({str(origin) for e in ordered for origin in (e.get("origin_domains") or ()) if origin}))
    counterexamples = tuple(str(e.get("episode_id", "")) for e in ordered if str(e.get("outcome", "")) in {"FAILED", "FALSIFIED"})
    patterns = analyze_repeated_agent_episodes(ordered)
    return CompiledExperience(len(incoming), len(ordered), len(origins), origins, counterexamples, patterns)
