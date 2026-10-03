"""Governed, advisory agent capability/routing and anti-pattern candidates."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping, Any, Tuple
from lola_repeated_episode import context_fingerprint


@dataclass(frozen=True)
class CapabilityEvidence:
    domain: str
    problem_class: str
    attempts: int
    verified_attempts: int
    recovered_attempts: int
    failures: int
    mean_information_gain: float
    evidence_quality: float
    duplicate_probe_rate: float
    mean_cost: float
    mean_latency: float


@dataclass(frozen=True)
class RoutingCandidate:
    context_fingerprint: str
    preferred_sequence: Tuple[str, ...]
    fallback_sequence: Tuple[str, ...]
    supporting_episode_ids: Tuple[str, ...]
    contradicting_episode_ids: Tuple[str, ...]
    status: str = "CANDIDATE"
    execution_authority: bool = False


@dataclass(frozen=True)
class AntiPatternCandidate:
    trigger: str
    behavior_to_avoid: str
    observed_consequence: str
    failure_episode_ids: Tuple[str, ...]
    recovery_episode_ids: Tuple[str, ...]
    status: str = "CANDIDATE"
    execution_authority: bool = False


def make_routing_candidate(context: Mapping[str, Any], preferred_sequence, fallback_sequence, supporting_episode_ids, contradicting_episode_ids):
    return RoutingCandidate(context_fingerprint(context), tuple(map(str, preferred_sequence)), tuple(map(str, fallback_sequence)), tuple(map(str, supporting_episode_ids)), tuple(map(str, contradicting_episode_ids)))


def make_antipattern_candidate(trigger, behavior_to_avoid, observed_consequence, failure_episode_ids, recovery_episode_ids):
    return AntiPatternCandidate(str(trigger), str(behavior_to_avoid), str(observed_consequence), tuple(map(str, failure_episode_ids)), tuple(map(str, recovery_episode_ids)))
