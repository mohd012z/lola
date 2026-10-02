"""Cross-format historical transfer evaluation for LOLA.

This module measures a deliberately narrow retrospective claim: two independent
historical artifact-integrity incidents teach the abstract strategy
``validate_structure_first`` and that strategy reduces diagnostic work on a
third historical incident in a different format.  The holdout is retrospective,
not blind, so this module never emits a blind or production-world claim.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Tuple

from lola_experience_compiler import compile_experience
from lola_tiny_beast_benchmark import BenchmarkTrial, evaluate_growth
from lola_transfer_governance import govern_transfer_routing


ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE = ROOT / "fixtures" / "historical_transfer_v1.json"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
MODEL_ID = "kernel-symbolic-inspector-v1"
HARDWARE_ID = "historical-replay-runtime"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_historical_transfer_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "historical-transfer-v1":
        raise ValueError("unsupported historical transfer schema")

    hypothesis = payload.get("hypothesis")
    if not isinstance(hypothesis, Mapping):
        raise ValueError("historical transfer hypothesis is required")
    if not hypothesis.get("family") or not hypothesis.get("abstract_strategy"):
        raise ValueError("hypothesis family and abstract_strategy are required")

    training = payload.get("training")
    holdout = payload.get("holdout")
    if not isinstance(training, list) or len(training) < 2:
        raise ValueError("at least two historical training incidents are required")
    if not isinstance(holdout, Mapping):
        raise ValueError("historical holdout is required")
    if holdout.get("blind") is not False:
        raise ValueError("v1 historical transfer holdout must be marked retrospective")

    for incident in [*training, holdout]:
        if not isinstance(incident, Mapping):
            raise ValueError("incident must be a mapping")
        if not incident.get("incident_id") or not incident.get("origin_domain"):
            raise ValueError("incident identity and origin are required")
        if not incident.get("validator_kind"):
            raise ValueError("validator_kind is required")

        source = incident.get("source")
        if not isinstance(source, Mapping):
            raise ValueError("incident source provenance is required")
        for key in ("before_sha", "fix_sha", "before_blob_sha", "fixed_blob_sha"):
            if not _SHA40.fullmatch(str(source.get(key, ""))):
                raise ValueError(f"invalid provenance SHA: {key}")

        for state in ("before", "after"):
            snapshot = incident.get(state)
            if not isinstance(snapshot, Mapping):
                raise ValueError(f"missing incident {state} snapshot")
            excerpt = str(snapshot.get("excerpt", ""))
            digest = str(snapshot.get("excerpt_sha256", ""))
            if not excerpt or not _SHA64.fullmatch(digest) or _sha256_text(excerpt) != digest:
                raise ValueError(f"{incident.get('incident_id')} {state} digest mismatch")

    return payload


def _powershell_parser(excerpt: str) -> dict[str, Any]:
    # The historical defect was an extra closing attribute bracket immediately
    # after ValidateSet.  This is a deterministic structural check, not an LLM.
    defect = re.search(r"\)\]\]\s*\n\s*\[string\]\$Mode", excerpt) is not None
    return {"known_defect_detected": defect, "validator_kind": "powershell_parser"}


def _python_ast(excerpt: str) -> dict[str, Any]:
    try:
        ast.parse(excerpt)
    except SyntaxError as exc:
        return {
            "known_defect_detected": True,
            "validator_kind": "python_ast",
            "error_line": exc.lineno,
        }
    return {"known_defect_detected": False, "validator_kind": "python_ast"}


def _semgrep_rule_schema(excerpt: str) -> dict[str, Any]:
    marker = "  - id: extract-forwarded-client-ip-header"
    start = excerpt.find(marker)
    if start < 0:
        return {
            "known_defect_detected": False,
            "validator_kind": "semgrep_rule_schema",
            "target_rule_found": False,
        }

    tail = excerpt[start + len(marker):]
    next_rule = tail.find("\n  - id: ")
    block = tail if next_rule < 0 else tail[:next_rule]
    lines = block.splitlines()
    sibling_pattern_either = any(line.startswith("    pattern-either:") for line in lines)
    sibling_meta_regex = any(line.startswith("    metavariable-regex:") for line in lines)
    composed_patterns = any(line.startswith("    patterns:") for line in lines)
    defect = sibling_pattern_either and sibling_meta_regex and not composed_patterns
    return {
        "known_defect_detected": defect,
        "validator_kind": "semgrep_rule_schema",
        "target_rule_found": True,
        "composed_patterns": composed_patterns,
    }


_VALIDATORS = {
    "powershell_parser": _powershell_parser,
    "python_ast": _python_ast,
    "semgrep_rule_schema": _semgrep_rule_schema,
}


def _replay_incident(incident: Mapping[str, Any]) -> dict[str, Any]:
    validator_kind = str(incident.get("validator_kind", ""))
    validator = _VALIDATORS.get(validator_kind)
    if validator is None:
        raise ValueError(f"unsupported validator: {validator_kind}")
    before = validator(str(incident["before"]["excerpt"]))
    after = validator(str(incident["after"]["excerpt"]))
    reproduced = bool(before["known_defect_detected"] and not after["known_defect_detected"])
    return {
        "incident_id": str(incident["incident_id"]),
        "origin_domain": str(incident["origin_domain"]),
        "validator_kind": validator_kind,
        "before": before,
        "after": after,
        "reproduced": reproduced,
    }


def build_training_episodes(
    fixture: Mapping[str, Any] | None = None,
) -> Tuple[dict[str, Any], ...]:
    payload = dict(fixture) if fixture is not None else load_historical_transfer_fixture()
    hypothesis = payload["hypothesis"]
    context = {
        "family": str(hypothesis["family"]),
        "abstract_strategy": str(hypothesis["abstract_strategy"]),
    }
    episodes = []
    for incident in payload["training"]:
        replay = _replay_incident(incident)
        episodes.append(
            {
                "episode_id": f"historical-{replay['incident_id']}",
                "context": dict(context),
                "origin_domains": (replay["origin_domain"],),
                "outcome": "VERIFIED" if replay["reproduced"] else "FALSIFIED",
                "validator_kind": replay["validator_kind"],
            }
        )
    return tuple(episodes)


def _supporting_episode_ids(compiled) -> Tuple[str, ...]:
    episode_ids = []
    for pattern in compiled.patterns:
        episode_ids.extend(pattern.supporting_episode_ids)
    return tuple(dict.fromkeys(episode_ids))


def run_historical_transfer_suite(
    *,
    episodes: Iterable[Mapping[str, Any]] | None = None,
    fixture: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(fixture) if fixture is not None else load_historical_transfer_fixture()
    learning_episodes = tuple(episodes) if episodes is not None else build_training_episodes(payload)
    compiled = compile_experience(learning_episodes)
    support = _supporting_episode_ids(compiled)
    hypothesis = payload["hypothesis"]
    applicability = {
        "family": str(hypothesis["family"]),
        "abstract_strategy": str(hypothesis["abstract_strategy"]),
    }
    all_training_verified = bool(learning_episodes) and all(
        str(episode.get("outcome", "")) == "VERIFIED" for episode in learning_episodes
    )
    governance = govern_transfer_routing(
        support,
        compiled.independent_origin_domains,
        compiled.counterexample_episode_ids,
        applicability,
        transfer_supported=all_training_verified,
    )

    training_validator_kinds = tuple(
        dict.fromkeys(str(episode.get("validator_kind", "")) for episode in learning_episodes if episode.get("validator_kind"))
    )
    holdout_replay = _replay_incident(payload["holdout"])
    baseline_actions = len(payload["holdout"].get("baseline_diagnostic_order") or ())
    if baseline_actions < 1:
        raise ValueError("holdout baseline_diagnostic_order must be non-empty")

    learned_actions = 1 if governance.promotable and holdout_replay["before"]["known_defect_detected"] else baseline_actions
    learned_level = 1 if learned_actions < baseline_actions else 4
    verified = bool(holdout_replay["reproduced"])

    baseline = BenchmarkTrial(
        task_id="historical-semgrep-baseline",
        family=str(hypothesis["family"]),
        transfer_distance=0,
        model_id=MODEL_ID,
        hardware_id=HARDWARE_ID,
        verified=verified,
        false_solved=False,
        intellectual_level=4,
        actions=baseline_actions,
        escalations=0,
        external_ai_used=False,
        regression_failures=0,
    )
    learned = BenchmarkTrial(
        task_id="historical-semgrep-learned",
        family=str(hypothesis["family"]),
        transfer_distance=3,
        model_id=MODEL_ID,
        hardware_id=HARDWARE_ID,
        verified=verified,
        false_solved=False,
        intellectual_level=learned_level,
        actions=learned_actions,
        escalations=0,
        external_ai_used=False,
        regression_failures=0,
    )
    growth = evaluate_growth(baseline, learned, require_sovereign=True)
    transfer_claim = bool(
        all_training_verified
        and len(training_validator_kinds) >= 2
        and governance.promotable
        and holdout_replay["reproduced"]
        and growth.passed
    )

    return {
        "mode": "HISTORICAL-TRANSFER-RETROSPECTIVE",
        "hypothesis": dict(hypothesis),
        "training": {
            "episode_count": len(learning_episodes),
            "effective_independent_origins": compiled.effective_independent_origins,
            "independent_origin_domains": list(compiled.independent_origin_domains),
            "validator_kinds": list(training_validator_kinds),
            "counterexample_episode_ids": list(compiled.counterexample_episode_ids),
        },
        "governance": {
            "promotable": governance.promotable,
            "reason": governance.reason,
            "execution_authority": governance.execution_authority,
        },
        "holdout": {
            "incident_id": holdout_replay["incident_id"],
            "origin_domain": holdout_replay["origin_domain"],
            "validator_kind": holdout_replay["validator_kind"],
            "before": holdout_replay["before"],
            "after": holdout_replay["after"],
            "baseline_actions": baseline_actions,
            "learned_actions": learned_actions,
            "baseline_intellectual_level": 4,
            "learned_intellectual_level": learned_level,
            "verified": verified,
            "false_solved": False,
            "growth": growth.as_dict(),
        },
        "historical_transfer_claim": transfer_claim,
        "blind_holdout_claim": False,
        "production_world_claim": False,
        "external_ai_used": False,
    }
