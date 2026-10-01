#!/usr/bin/env python3
"""Hybrid cognitive fabric for Lola / Kernel_AI / IN_AI.

Stdlib-only reference implementation. It does not execute arbitrary remote commands.
External inputs are normalized into evidence-bearing KIP envelopes before they may
influence cognitive state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import threading


class Kind(str, Enum):
    OBSERVATION = "observation"
    STATE = "state"
    QUERY = "query"
    COMMAND = "command"
    RESULT = "result"
    EVIDENCE = "evidence"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    CAPABILITY = "capability"


class PathClass(str, Enum):
    FAST = "fast"
    COGNITIVE = "cognitive"
    DURABLE = "durable"


@dataclass(frozen=True)
class KIPEnvelope:
    """Transport-independent Kernel Intelligence Protocol envelope."""

    kind: str
    topic: str
    source: str
    payload: dict[str, Any]
    id: str = ""
    task_id: str = ""
    correlation_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sequence: int = 0
    reliability: float = 0.5
    priority: int = 2
    direct: bool = False
    durable: bool = False
    version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.id:
            raw = f"{self.source}|{self.topic}|{self.timestamp}|{self.sequence}|{self.payload}"
            object.__setattr__(self, "id", hashlib.sha256(raw.encode()).hexdigest()[:20])
        object.__setattr__(self, "reliability", max(0.0, min(1.0, float(self.reliability))))
        object.__setattr__(self, "priority", max(0, min(4, int(self.priority))))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceProfile:
    source_id: str
    capabilities: set[str] = field(default_factory=set)
    reliability: float = 0.5
    last_seen: str = ""
    transport: str = "internal"


class SourceRegistry:
    """Capability discovery + evidence-source reliability."""

    def __init__(self) -> None:
        self.sources: dict[str, SourceProfile] = {}

    def register(self, source_id: str, capabilities: Iterable[str], *, reliability: float = 0.5,
                 transport: str = "internal") -> SourceProfile:
        profile = SourceProfile(source_id, set(capabilities), max(0.0, min(1.0, reliability)),
                                datetime.now(timezone.utc).isoformat(), transport)
        self.sources[source_id] = profile
        return profile

    def select(self, capability: str) -> list[SourceProfile]:
        return sorted(
            (s for s in self.sources.values() if capability in s.capabilities),
            key=lambda s: s.reliability,
            reverse=True,
        )


class EventStore:
    """Append-only JSONL store for replay, recovery, and training episodes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._seen: set[str] = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    self._seen.add(json.loads(line)["id"])
                except (ValueError, KeyError, TypeError):
                    continue

    def append(self, event: KIPEnvelope) -> bool:
        if event.id in self._seen:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if event.id in self._seen:
                return False
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
            self._seen.add(event.id)
        return True

    def replay(self, task_id: str = "") -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if not task_id or item.get("task_id") == task_id:
                out.append(item)
        return out


@dataclass
class Observation:
    event_id: str
    source: str
    topic: str
    payload: dict[str, Any]
    reliability: float
    direct: bool
    timestamp: str


@dataclass
class CognitiveState:
    task_id: str
    objective: str = ""
    observations: list[Observation] = field(default_factory=list)
    unknowns: set[str] = field(default_factory=set)
    assumptions: set[str] = field(default_factory=set)
    contradictions: list[str] = field(default_factory=list)
    hypotheses: dict[str, str] = field(default_factory=dict)
    predictions: dict[str, str] = field(default_factory=dict)
    world: dict[str, Any] = field(default_factory=dict)
    verified_claims: set[str] = field(default_factory=set)


class HybridRouter:
    """Select fast/cognitive/durable processing without coupling cognition to transport."""

    FAST_PREFIXES = ("heartbeat.", "progress.", "telemetry.")
    COGNITIVE_PREFIXES = ("error.", "runtime.", "build.failure", "test.failure", "evidence.")

    def classify(self, event: KIPEnvelope) -> set[PathClass]:
        paths: set[PathClass] = set()
        if event.durable or event.kind in {Kind.EVIDENCE.value, Kind.RESULT.value, Kind.ERROR.value}:
            paths.add(PathClass.DURABLE)
        if event.topic.startswith(self.FAST_PREFIXES) or event.kind == Kind.HEARTBEAT.value:
            paths.add(PathClass.FAST)
        if event.topic.startswith(self.COGNITIVE_PREFIXES) or event.kind in {
            Kind.OBSERVATION.value, Kind.EVIDENCE.value, Kind.ERROR.value
        }:
            paths.add(PathClass.COGNITIVE)
        if not paths:
            paths.add(PathClass.FAST)
        return paths


class MetaController:
    """L5 deterministic governor: reliability is evidence-derived, not model self-rating."""

    @staticmethod
    def metrics(state: CognitiveState) -> dict[str, float | int | bool]:
        obs = state.observations
        direct = sum(1 for x in obs if x.direct)
        avg_rel = sum(x.reliability for x in obs) / len(obs) if obs else 0.0
        contradiction_rate = len(state.contradictions) / max(1, len(obs))
        evidence_coverage = direct / max(1, len(obs))
        epistemic_fuse = contradiction_rate > 0.25 or avg_rel < 0.45
        return {
            "observations": len(obs),
            "unknowns": len(state.unknowns),
            "assumptions": len(state.assumptions),
            "contradictions": len(state.contradictions),
            "average_reliability": round(avg_rel, 4),
            "evidence_coverage": round(evidence_coverage, 4),
            "contradiction_rate": round(contradiction_rate, 4),
            "epistemic_fuse": epistemic_fuse,
        }

    def decision(self, state: CognitiveState) -> str:
        m = self.metrics(state)
        if m["epistemic_fuse"]:
            return "CROSSCHECK"
        if state.unknowns:
            return "CONTINUE"
        if state.assumptions:
            return "FALSIFY"
        return "VERIFY"


class CognitiveFabric:
    """L1/L2/L5 foundation used by IN_AI reasoning and future transport adapters."""

    def __init__(self, event_store: str | Path) -> None:
        self.registry = SourceRegistry()
        self.router = HybridRouter()
        self.meta = MetaController()
        self.events = EventStore(event_store)
        self.states: dict[str, CognitiveState] = {}
        self._processed: set[str] = set()

    def state(self, task_id: str, objective: str = "") -> CognitiveState:
        if task_id not in self.states:
            self.states[task_id] = CognitiveState(task_id=task_id, objective=objective)
        elif objective:
            self.states[task_id].objective = objective
        return self.states[task_id]

    def ingest(self, event: KIPEnvelope) -> dict[str, Any]:
        """Trust boundary: normalize once, deduplicate, persist if needed, then update cognition."""
        paths = self.router.classify(event)
        if event.id in self._processed:
            return {"accepted": False, "reason": "duplicate", "id": event.id}
        self._processed.add(event.id)
        if PathClass.DURABLE in paths:
            self.events.append(event)

        state = self.state(event.task_id or "global")
        if PathClass.COGNITIVE in paths:
            state.observations.append(Observation(
                event.id, event.source, event.topic, dict(event.payload), event.reliability,
                event.direct, event.timestamp,
            ))
            self._update_world(state, event)
        return {
            "accepted": True,
            "id": event.id,
            "paths": sorted(x.value for x in paths),
            "meta": self.meta.metrics(state),
            "next": self.meta.decision(state),
        }

    @staticmethod
    def _update_world(state: CognitiveState, event: KIPEnvelope) -> None:
        """L2 compact state projection. Contradicting direct observations trip L5 crosscheck."""
        entity = str(event.payload.get("entity", ""))
        prop = str(event.payload.get("property", ""))
        if not entity or not prop or "value" not in event.payload:
            return
        key = f"{entity}.{prop}"
        value = event.payload["value"]
        previous = state.world.get(key)
        if previous is not None and previous != value and event.direct:
            state.contradictions.append(f"{key}: {previous!r} != {value!r}")
        state.world[key] = value

    def causal_delta(self, task_id: str, expected: list[tuple[str, Any]]) -> dict[str, Any]:
        """New primitive: locate the first expected→actual divergence in an ordered chain."""
        state = self.state(task_id)
        for index, (key, wanted) in enumerate(expected):
            actual = state.world.get(key, "<UNKNOWN>")
            if actual != wanted:
                return {"index": index, "key": key, "expected": wanted, "actual": actual}
        return {"index": -1, "status": "no_divergence"}

    def snapshot(self, task_id: str) -> dict[str, Any]:
        state = self.state(task_id)
        return {
            "task_id": state.task_id,
            "objective": state.objective,
            "world": dict(state.world),
            "unknowns": sorted(state.unknowns),
            "assumptions": sorted(state.assumptions),
            "contradictions": list(state.contradictions),
            "meta": self.meta.metrics(state),
            "next": self.meta.decision(state),
        }
