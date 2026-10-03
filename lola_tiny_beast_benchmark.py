"""Deterministic Tiny-to-Beast benchmark for LOLA system-intelligence gain.

This module measures architecture-level improvement while holding model and
hardware identity fixed.  It deliberately reports raw deltas instead of a
single vanity intelligence score.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, Tuple


@dataclass(frozen=True)
class BenchmarkTrial:
    task_id: str
    family: str
    transfer_distance: int
    model_id: str
    hardware_id: str
    verified: bool
    false_solved: bool = False
    intellectual_level: int = 0
    actions: int = 0
    escalations: int = 0
    tokens: int = 0
    wall_time_ms: int = 0
    external_ai_used: bool = False
    regression_failures: int = 0


@dataclass(frozen=True)
class GrowthResult:
    passed: bool
    status: str
    reasons: Tuple[str, ...] = field(default_factory=tuple)
    intellectual_downshift: int = 0
    action_delta: int = 0
    escalation_delta: int = 0
    token_delta: int = 0
    wall_time_delta_ms: int = 0
    transfer_distance: int = 0
    sovereign: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _trial_from_mapping(value: Mapping[str, Any]) -> BenchmarkTrial:
    required = (
        "task_id",
        "family",
        "transfer_distance",
        "model_id",
        "hardware_id",
        "verified",
        "intellectual_level",
        "actions",
    )
    missing = [key for key in required if key not in value]
    if missing:
        raise ValueError("missing benchmark fields: " + ", ".join(missing))

    trial = BenchmarkTrial(
        task_id=str(value["task_id"]),
        family=str(value["family"]),
        transfer_distance=int(value["transfer_distance"]),
        model_id=str(value["model_id"]),
        hardware_id=str(value["hardware_id"]),
        verified=bool(value["verified"]),
        false_solved=bool(value.get("false_solved", False)),
        intellectual_level=int(value["intellectual_level"]),
        actions=int(value["actions"]),
        escalations=int(value.get("escalations", 0)),
        tokens=int(value.get("tokens", 0)),
        wall_time_ms=int(value.get("wall_time_ms", 0)),
        external_ai_used=bool(value.get("external_ai_used", False)),
        regression_failures=int(value.get("regression_failures", 0)),
    )
    if trial.transfer_distance < 0:
        raise ValueError("transfer_distance must be >= 0")
    for name in (
        "intellectual_level",
        "actions",
        "escalations",
        "tokens",
        "wall_time_ms",
        "regression_failures",
    ):
        if getattr(trial, name) < 0:
            raise ValueError(f"{name} must be >= 0")
    return trial


def load_benchmark_pair(path: Path | str) -> tuple[BenchmarkTrial, BenchmarkTrial]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, Mapping):
        raise ValueError("benchmark document must be a JSON object")
    baseline = data.get("baseline")
    learned = data.get("learned")
    if not isinstance(baseline, Mapping) or not isinstance(learned, Mapping):
        raise ValueError("benchmark document requires baseline and learned objects")
    return _trial_from_mapping(baseline), _trial_from_mapping(learned)


def evaluate_growth(
    baseline: BenchmarkTrial,
    learned: BenchmarkTrial,
    *,
    require_sovereign: bool = False,
    minimum_transfer_distance: int = 2,
) -> GrowthResult:
    """Evaluate whether learned cognition demonstrates system intelligence gain.

    A pass means the same model on the same hardware solved a verified unseen
    variant at lower intellectual level and lower/equal action+escalation cost,
    without false-solved or regression evidence.  T2+ transfer is required by
    default so exact/near-exact replay cannot masquerade as generalization.
    """

    reasons: list[str] = []
    if baseline.family != learned.family:
        reasons.append("task_family_changed")
    if baseline.model_id != learned.model_id:
        reasons.append("model_changed")
    if baseline.hardware_id != learned.hardware_id:
        reasons.append("hardware_changed")
    if not baseline.verified:
        reasons.append("baseline_not_verified")
    if not learned.verified:
        reasons.append("learned_not_verified")
    if learned.false_solved:
        reasons.append("false_solved")
    if learned.regression_failures:
        reasons.append("regression_failure")
    if learned.transfer_distance < minimum_transfer_distance:
        reasons.append("transfer_distance_below_t2")
    if learned.intellectual_level >= baseline.intellectual_level:
        reasons.append("no_intellectual_downshift")
    if learned.actions > baseline.actions:
        reasons.append("actions_increased")
    if learned.escalations > baseline.escalations:
        reasons.append("escalations_increased")
    if baseline.tokens and learned.tokens > baseline.tokens:
        reasons.append("tokens_increased")
    if baseline.wall_time_ms and learned.wall_time_ms > baseline.wall_time_ms:
        reasons.append("wall_time_increased")
    if require_sovereign and learned.external_ai_used:
        reasons.append("external_ai_used")

    passed = not reasons
    return GrowthResult(
        passed=passed,
        status="SYSTEM_INTELLIGENCE_GAIN" if passed else "NOT_PROVEN",
        reasons=tuple(reasons),
        intellectual_downshift=baseline.intellectual_level - learned.intellectual_level,
        action_delta=learned.actions - baseline.actions,
        escalation_delta=learned.escalations - baseline.escalations,
        token_delta=learned.tokens - baseline.tokens,
        wall_time_delta_ms=learned.wall_time_ms - baseline.wall_time_ms,
        transfer_distance=learned.transfer_distance,
        sovereign=not learned.external_ai_used,
    )


def run_tiny_beast_smoke() -> dict[str, Any]:
    """Exercise benchmark semantics with deterministic synthetic trials.

    Passing this smoke proves the benchmark harness works.  It does not prove
    that a real model/runtime has achieved Tiny-to-Beast learning.
    """

    baseline = BenchmarkTrial(
        task_id="smoke-baseline",
        family="dependency-debug",
        transfer_distance=0,
        model_id="fixed-tiny-model",
        hardware_id="fixed-local-hardware",
        verified=True,
        false_solved=False,
        intellectual_level=4,
        actions=18,
        escalations=2,
        tokens=10000,
        wall_time_ms=12000,
        external_ai_used=False,
        regression_failures=0,
    )
    learned = BenchmarkTrial(
        task_id="smoke-t2",
        family="dependency-debug",
        transfer_distance=2,
        model_id="fixed-tiny-model",
        hardware_id="fixed-local-hardware",
        verified=True,
        false_solved=False,
        intellectual_level=1,
        actions=4,
        escalations=0,
        tokens=1800,
        wall_time_ms=3500,
        external_ai_used=False,
        regression_failures=0,
    )
    result = evaluate_growth(baseline, learned, require_sovereign=True)
    payload = result.as_dict()
    payload.update(
        {
            "mode": "HARNESS-SMOKE",
            "empirical_beast_claim": False,
            "baseline_task_id": baseline.task_id,
            "learned_task_id": learned.task_id,
        }
    )
    return payload
