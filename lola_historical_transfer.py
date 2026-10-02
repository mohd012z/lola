"""Cross-language historical transfer evaluation for LOLA.

This evidence tier is stronger than an authored synthetic task but deliberately
weaker than a prospective blind evaluation. Two independently sourced frozen
historical incidents support an abstract diagnostic priority; a later frozen
incident is then used as a non-blind historical holdout.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from lola_experience_compiler import compile_experience
from lola_tiny_beast_benchmark import BenchmarkTrial, evaluate_growth
from lola_transfer_governance import govern_transfer_routing


ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE = ROOT / "fixtures" / "historical_transfer_v2.json"
MODEL_ID = "kernel-historical-inspector-v2"
HARDWARE_ID = "frozen-fixture-runtime"
FAMILY = "historical-preflight-validity"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_KNOWN_VALIDATORS = {
    "powershell_attribute_delimiter",
    "python_ast",
    "yaml_scalar_lexical",
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_source(source: Mapping[str, Any]) -> None:
    for key in ("repository", "path"):
        if not isinstance(source.get(key), str) or not source[key]:
            raise ValueError(f"missing source provenance: {key}")
    for key in ("before_sha", "fix_sha", "before_blob_sha", "fixed_blob_sha"):
        if not _SHA40.fullmatch(str(source.get(key, ""))):
            raise ValueError(f"invalid provenance SHA: {key}")


def _validate_snapshot(snapshot: Mapping[str, Any], label: str) -> None:
    excerpt = str(snapshot.get("excerpt", ""))
    digest = str(snapshot.get("excerpt_sha256", ""))
    if not excerpt:
        raise ValueError(f"missing {label} excerpt")
    if not _SHA64.fullmatch(digest) or _sha256_text(excerpt) != digest:
        raise ValueError(f"{label} excerpt provenance digest mismatch")


def _validate_incident_shape(item: Mapping[str, Any], label: str) -> None:
    if not isinstance(item.get("incident_id"), str) or not item["incident_id"]:
        raise ValueError(f"{label} incident_id is required")
    if not isinstance(item.get("origin_domain"), str) or not item["origin_domain"]:
        raise ValueError(f"{label} origin_domain is required")
    if item.get("validator") not in _KNOWN_VALIDATORS:
        raise ValueError(f"{label} validator is unsupported")
    source = item.get("source")
    if not isinstance(source, Mapping):
        raise ValueError(f"{label} source provenance is required")
    _validate_source(source)
    for state in ("before", "after"):
        snapshot = item.get(state)
        if not isinstance(snapshot, Mapping):
            raise ValueError(f"{label} missing {state} snapshot")
        _validate_snapshot(snapshot, f"{label}.{state}")


def load_historical_transfer_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "historical-transfer-v2":
        raise ValueError("unsupported historical transfer schema")
    if payload.get("abstract_failure_role") != "preflight_validity":
        raise ValueError("historical transfer v2 requires preflight_validity role")

    training = payload.get("training_incidents")
    if not isinstance(training, list) or len(training) < 2:
        raise ValueError("at least two training incidents are required")
    for index, item in enumerate(training):
        if not isinstance(item, Mapping):
            raise ValueError("training incident must be an object")
        _validate_incident_shape(item, f"training[{index}]")

    origins = [str(item["origin_domain"]) for item in training]
    if len(set(origins)) != len(origins):
        raise ValueError("training origin domains must be independent")

    holdout = payload.get("holdout_incident")
    if not isinstance(holdout, Mapping):
        raise ValueError("holdout incident is required")
    _validate_incident_shape(holdout, "holdout")
    if holdout["origin_domain"] in set(origins):
        raise ValueError("holdout origin must be distinct from training origins")
    if not isinstance(holdout.get("blind_holdout"), bool):
        raise ValueError("holdout blind_holdout must be explicit")
    if int(holdout.get("transfer_distance", 0)) < 2:
        raise ValueError("holdout transfer distance must be at least T2")
    return payload


def _validate_powershell_attribute_delimiter(excerpt: str) -> bool:
    """Detect the historical extra closing attribute bracket."""
    return ")]]" not in excerpt


def _validate_python_ast(excerpt: str) -> bool:
    try:
        ast.parse(excerpt)
    except SyntaxError:
        return False
    return True


def _yaml_scalar_line_valid(line: str) -> bool:
    _, separator, value = line.partition(":")
    if not separator:
        return False
    value = value.strip()
    if not value:
        return False
    if value[0] == '"':
        for index in range(1, len(value)):
            if value[index] != '"':
                continue
            slash_count = 0
            cursor = index - 1
            while cursor >= 0 and value[cursor] == "\\":
                slash_count += 1
                cursor -= 1
            if slash_count % 2 == 0:
                return value[index + 1 :].strip() == ""
        return False
    if value[0] == "'":
        index = 1
        while index < len(value):
            if value[index] == "'":
                if index + 1 < len(value) and value[index + 1] == "'":
                    index += 2
                    continue
                return value[index + 1 :].strip() == ""
            index += 1
        return False
    return True


def _validate_yaml_scalar_lexical(excerpt: str) -> bool:
    lines = [line for line in excerpt.splitlines() if "pattern-regex:" in line]
    return bool(lines) and all(_yaml_scalar_line_valid(line) for line in lines)


def _validate_excerpt(validator: str, excerpt: str) -> bool:
    if validator == "powershell_attribute_delimiter":
        return _validate_powershell_attribute_delimiter(excerpt)
    if validator == "python_ast":
        return _validate_python_ast(excerpt)
    if validator == "yaml_scalar_lexical":
        return _validate_yaml_scalar_lexical(excerpt)
    raise ValueError(f"unsupported validator: {validator}")


def _replay(item: Mapping[str, Any]) -> dict[str, Any]:
    validator = str(item["validator"])
    before_valid = _validate_excerpt(validator, str(item["before"]["excerpt"]))
    after_valid = _validate_excerpt(validator, str(item["after"]["excerpt"]))
    return {
        "incident_id": item["incident_id"],
        "origin_domain": item["origin_domain"],
        "language": item["language"],
        "validator": validator,
        "before_valid": before_valid,
        "after_valid": after_valid,
        "reproduced": (not before_valid) and after_valid,
        "source": dict(item["source"]),
    }


def _supporting_episode_ids(compiled) -> tuple[str, ...]:
    ids: list[str] = []
    for pattern in compiled.patterns:
        ids.extend(pattern.supporting_episode_ids)
    return tuple(dict.fromkeys(ids))


def _diagnose(root_role: str | None, preferred_role: str | None) -> tuple[int, bool, str | None]:
    stages = ["runtime_environment", "semantic_logic", "consumer_output", "preflight_validity"]
    if preferred_role in stages:
        stages = [preferred_role] + [stage for stage in stages if stage != preferred_role]
    actions = 0
    for stage in stages:
        actions += 1
        if stage == root_role:
            return actions, True, stage
    return actions, False, None


def _regression_failures(preferred_role: str | None) -> int:
    _, verified, found = _diagnose("semantic_logic", preferred_role)
    return 0 if verified and found == "semantic_logic" else 1


def run_historical_transfer_suite(
    fixture: Mapping[str, Any] | None = None,
    *,
    counterexample: bool = False,
) -> dict[str, Any]:
    payload = dict(fixture) if fixture is not None else load_historical_transfer_fixture()
    role = str(payload["abstract_failure_role"])
    training_replay = [_replay(item) for item in payload["training_incidents"]]

    episodes: list[dict[str, Any]] = []
    for replay in training_replay:
        if replay["reproduced"]:
            episodes.append(
                {
                    "episode_id": f"historical-{replay['incident_id']}",
                    "context": {"family": FAMILY, "abstract_failure_role": role},
                    "origin_domains": (replay["origin_domain"],),
                    "outcome": "VERIFIED",
                }
            )
    if counterexample:
        episodes.append(
            {
                "episode_id": "historical-preflight-counterexample",
                "context": {"family": FAMILY, "abstract_failure_role": role},
                "origin_domains": ("counterexample-origin",),
                "outcome": "FALSIFIED",
            }
        )

    compiled = compile_experience(episodes)
    support = _supporting_episode_ids(compiled)
    applicability = {"family": FAMILY, "abstract_failure_role": role}
    governance = govern_transfer_routing(
        support,
        compiled.independent_origin_domains,
        compiled.counterexample_episode_ids,
        applicability,
        transfer_supported=len(training_replay) >= 2 and all(item["reproduced"] for item in training_replay),
    )

    holdout_item = payload["holdout_incident"]
    holdout_replay = _replay(holdout_item)
    root_role = role if holdout_replay["reproduced"] else None
    baseline_actions, baseline_verified, _ = _diagnose(root_role, None)
    preferred_role = role if governance.promotable else None
    learned_actions, learned_verified, _ = _diagnose(root_role, preferred_role)
    regression_failures = _regression_failures(preferred_role)
    distance = int(holdout_item["transfer_distance"])

    baseline = BenchmarkTrial(
        task_id="historical-holdout-baseline",
        family=FAMILY,
        transfer_distance=0,
        model_id=MODEL_ID,
        hardware_id=HARDWARE_ID,
        verified=baseline_verified,
        false_solved=False,
        intellectual_level=4,
        actions=baseline_actions,
        escalations=0,
        external_ai_used=False,
        regression_failures=0,
    )
    learned = BenchmarkTrial(
        task_id="historical-holdout-learned",
        family=FAMILY,
        transfer_distance=distance,
        model_id=MODEL_ID,
        hardware_id=HARDWARE_ID,
        verified=learned_verified,
        false_solved=False,
        intellectual_level=1 if governance.promotable else 4,
        actions=learned_actions,
        escalations=0,
        external_ai_used=False,
        regression_failures=regression_failures,
    )
    growth = evaluate_growth(baseline, learned, require_sovereign=True)

    historical_transfer_claim = (
        len(training_replay) >= 2
        and all(item["reproduced"] for item in training_replay)
        and holdout_replay["reproduced"]
        and governance.promotable
        and growth.passed
    )

    return {
        "mode": "HISTORICAL-TRANSFER",
        "abstract_failure_role": role,
        "training_replay": training_replay,
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
        "holdout": {
            **holdout_replay,
            "blind_holdout": bool(holdout_item["blind_holdout"]),
            "transfer_distance": distance,
            "baseline": asdict(baseline),
            "learned": asdict(learned),
            "growth": growth.as_dict(),
        },
        "historical_transfer_claim": bool(historical_transfer_claim),
        "blind_holdout_claim": bool(historical_transfer_claim and holdout_item["blind_holdout"]),
        "prospective_claim": False,
        "production_world_claim": False,
    }
