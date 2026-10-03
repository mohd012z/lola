"""Controlled empirical T2/T3 transfer benchmark for LOLA learning.

This suite exercises the real experience compiler and transfer-governance path,
then measures diagnostic actions before and after governed learning. It is a
controlled architecture benchmark, not a production-world intelligence claim.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Any, Tuple

from lola_experience_compiler import compile_experience
from lola_tiny_beast_benchmark import BenchmarkTrial, evaluate_growth
from lola_transfer_governance import govern_transfer_routing


MODEL_ID = "kernel-symbolic-inspector-v1"
HARDWARE_ID = "controlled-python-runtime"
FAMILY = "causal-pipeline-debug"


@dataclass(frozen=True)
class DiagnosticStage:
    stage_id: str
    role: str
    healthy: bool = True


@dataclass(frozen=True)
class DiagnosticResult:
    found_role: str | None
    actions: int
    verified: bool
    false_solved: bool


def build_verified_learning_episodes() -> Tuple[dict[str, Any], ...]:
    """Independent verified episodes supporting one abstract failure role."""
    context = {"family": FAMILY, "abstract_failure_role": "artifact"}
    return (
        {
            "episode_id": "learn-artifact-a",
            "context": dict(context),
            "origin_domains": ("independent-a",),
            "outcome": "VERIFIED",
        },
        {
            "episode_id": "learn-artifact-b",
            "context": dict(context),
            "origin_domains": ("independent-b",),
            "outcome": "VERIFIED",
        },
    )


def _task(transfer_distance: int) -> Tuple[DiagnosticStage, ...]:
    if transfer_distance == 2:
        return (
            DiagnosticStage("ingest-v2", "source"),
            DiagnosticStage("normalize-v2", "transform"),
            DiagnosticStage("cache-v2", "cache"),
            DiagnosticStage("bundle-v2", "artifact", False),
            DiagnosticStage("consumer-v2", "consumer"),
        )
    if transfer_distance == 3:
        return (
            DiagnosticStage("sensor-v3", "source"),
            DiagnosticStage("decode-v3", "transform"),
            DiagnosticStage("policy-v3", "policy"),
            DiagnosticStage("index-v3", "index"),
            DiagnosticStage("package-v3", "artifact", False),
            DiagnosticStage("loader-v3", "consumer"),
            DiagnosticStage("runtime-v3", "runtime"),
        )
    raise ValueError("controlled suite only defines T2 and T3 tasks")


def _inspect(stages: Tuple[DiagnosticStage, ...], preferred_role: str | None = None) -> DiagnosticResult:
    ordered = list(stages)
    if preferred_role:
        preferred = [stage for stage in ordered if stage.role == preferred_role]
        remaining = [stage for stage in ordered if stage.role != preferred_role]
        ordered = preferred + remaining

    actions = 0
    for stage in ordered:
        actions += 1
        if not stage.healthy:
            return DiagnosticResult(stage.role, actions, True, False)
    return DiagnosticResult(None, actions, False, False)


def _regression_failures(preferred_role: str | None) -> int:
    """Ensure a learned priority does not prevent finding another failure role."""
    regression = (
        DiagnosticStage("r-source", "source"),
        DiagnosticStage("r-transform", "transform", False),
        DiagnosticStage("r-artifact", "artifact"),
        DiagnosticStage("r-runtime", "runtime"),
    )
    result = _inspect(regression, preferred_role)
    return 0 if result.verified and result.found_role == "transform" else 1


def _supporting_episode_ids(compiled) -> Tuple[str, ...]:
    ids = []
    for pattern in compiled.patterns:
        ids.extend(pattern.supporting_episode_ids)
    return tuple(dict.fromkeys(ids))


def run_controlled_transfer_suite(*, episodes: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    learning_episodes = tuple(episodes) if episodes is not None else build_verified_learning_episodes()
    compiled = compile_experience(learning_episodes)
    support = _supporting_episode_ids(compiled)
    applicability = {"family": FAMILY, "abstract_failure_role": "artifact"}
    governance = govern_transfer_routing(
        support,
        compiled.independent_origin_domains,
        compiled.counterexample_episode_ids,
        applicability,
        transfer_supported=True,
    )

    preferred_role = applicability["abstract_failure_role"] if governance.promotable else None
    trials = []
    for distance in (2, 3):
        stages = _task(distance)
        baseline_result = _inspect(stages)
        learned_result = _inspect(stages, preferred_role)
        regressions = _regression_failures(preferred_role)

        baseline = BenchmarkTrial(
            task_id=f"controlled-t{distance}-baseline",
            family=FAMILY,
            transfer_distance=0,
            model_id=MODEL_ID,
            hardware_id=HARDWARE_ID,
            verified=baseline_result.verified,
            false_solved=baseline_result.false_solved,
            intellectual_level=4,
            actions=baseline_result.actions,
            escalations=0,
            external_ai_used=False,
            regression_failures=0,
        )
        learned = BenchmarkTrial(
            task_id=f"controlled-t{distance}-learned",
            family=FAMILY,
            transfer_distance=distance,
            model_id=MODEL_ID,
            hardware_id=HARDWARE_ID,
            verified=learned_result.verified,
            false_solved=learned_result.false_solved,
            intellectual_level=1 if governance.promotable else 4,
            actions=learned_result.actions,
            escalations=0,
            external_ai_used=False,
            regression_failures=regressions,
        )
        growth = evaluate_growth(baseline, learned, require_sovereign=True)
        trials.append(
            {
                "transfer_distance": distance,
                "baseline": asdict(baseline),
                "learned": asdict(learned),
                "growth": growth.as_dict(),
            }
        )

    controlled_claim = governance.promotable and all(t["growth"]["passed"] for t in trials)
    return {
        "mode": "CONTROLLED-EMPIRICAL",
        "controlled_empirical_claim": controlled_claim,
        "production_world_claim": False,
        "compiled": {
            "input_episode_count": compiled.input_episode_count,
            "unique_episode_count": compiled.unique_episode_count,
            "effective_independent_origins": compiled.effective_independent_origins,
            "independent_origin_domains": list(compiled.independent_origin_domains),
            "counterexample_episode_ids": list(compiled.counterexample_episode_ids),
        },
        "governance": {
            "promotable": governance.promotable,
            "reason": governance.reason,
            "execution_authority": governance.execution_authority,
        },
        "trials": trials,
    }
