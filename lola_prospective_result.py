"""Phase-B governance for LOLA's preregistered prospective transfer test.

The Phase-A preregistration is immutable and anchored at ANCHOR_SHA.  A future
result is valid only when it references that prior anchor and seal, obeys the
first-eligible selection policy, proves commit chronology, and authenticates the
selection-lock artifact committed before repair.  A valid failed trial remains
evidence; it is never upgraded into a success claim.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from lola_tiny_beast_benchmark import BenchmarkTrial, evaluate_growth


ANCHOR_SHA = "2830d1d4a45204787201fceafb81ac0e7cdc6331"
PREREGISTRATION_SEAL = "0ad03ed5ba5c017e764ad43caeb1970e54d3bf81d64f367eb14320974d9ea46f"
REGISTRATION_ID = "lola-preflight-validity-prospective-001"
MODEL_ID = "kernel-historical-inspector-v2"
HARDWARE_ID = "frozen-fixture-runtime"
FAMILY = "historical-preflight-validity"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_SURFACES = {"source", "workflow", "config", "runtime-integration"}


def _git_is_ancestor(repo: Path, older: str, newer: str) -> bool:
    if not (_SHA40.fullmatch(older) and _SHA40.fullmatch(newer)):
        return False
    completed = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def verify_commit_order(
    repository_root: Path | str,
    anchor_sha: str,
    failure_sha: str,
    selection_lock_sha: str,
    fix_sha: str,
    result_sha: str,
) -> bool:
    """Require strict anchor -> failure -> selection -> fix -> result ancestry."""

    repo = Path(repository_root).resolve()
    chain = (anchor_sha, failure_sha, selection_lock_sha, fix_sha, result_sha)
    if len(set(chain)) != len(chain):
        return False
    if not all(_SHA40.fullmatch(value) for value in chain):
        return False
    return all(
        _git_is_ancestor(repo, older, newer)
        for older, newer in zip(chain, chain[1:])
    )


def _canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_repo_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip() or "\\" in value or "\x00" in value:
        return None
    path = PurePosixPath(value.strip())
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _load_json_from_commit(repo: Path, commit_sha: str, path: str) -> dict[str, Any] | None:
    if not _SHA40.fullmatch(commit_sha):
        return None
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit_sha}:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _selection_lock_reasons(
    lock: Mapping[str, Any],
    *,
    expected_anchor_sha: str,
    expected_failure_sha: str,
    result_selection: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    payload = dict(lock)

    if payload.get("schema_version") != "prospective-holdout-selection-lock-v1":
        reasons.append("selection_lock_schema_invalid")
    if payload.get("registration_id") != REGISTRATION_ID:
        reasons.append("selection_lock_registration_mismatch")
    if payload.get("phase") != "SELECTION_LOCK":
        reasons.append("selection_lock_phase_invalid")
    if payload.get("status") != "LOCKED_AWAITING_REPAIR":
        reasons.append("selection_lock_status_invalid")
    if payload.get("preregistration_anchor_sha") != expected_anchor_sha:
        reasons.append("selection_lock_anchor_mismatch")
    if payload.get("preregistration_seal_sha256") != PREREGISTRATION_SEAL:
        reasons.append("selection_lock_seal_mismatch")
    if payload.get("failure_commit_sha") != expected_failure_sha:
        reasons.append("selection_lock_failure_mismatch")

    supplied_digest = str(payload.get("selection_lock_digest_sha256") or "")
    if not _SHA256.fullmatch(supplied_digest):
        reasons.append("selection_lock_digest_missing_or_invalid")
    else:
        unsigned = dict(payload)
        unsigned.pop("selection_lock_digest_sha256", None)
        if _canonical_digest(unsigned) != supplied_digest:
            reasons.append("selection_lock_digest_mismatch")

    for field, reason in (
        ("candidate_digest_sha256", "selection_lock_candidate_digest_invalid"),
        ("observation_digest_sha256", "selection_lock_observation_digest_invalid"),
        ("eligibility_review_digest_sha256", "selection_lock_review_digest_invalid"),
    ):
        if not _SHA256.fullmatch(str(payload.get(field) or "")):
            reasons.append(reason)
    if not str(payload.get("eligibility_reviewer_id") or "").strip():
        reasons.append("selection_lock_reviewer_missing")

    lock_selection = payload.get("selection")
    if not isinstance(lock_selection, Mapping):
        reasons.append("selection_lock_selection_missing")
        lock_selection = {}
    if dict(lock_selection) != dict(result_selection):
        reasons.append("selection_lock_selection_mismatch")

    if lock_selection.get("surface") not in _ALLOWED_SURFACES:
        reasons.append("selection_lock_surface_invalid")
    before_refs = lock_selection.get("before_evidence_refs")
    if (
        not isinstance(before_refs, list)
        or not before_refs
        or not all(isinstance(item, str) and item.strip() for item in before_refs)
    ):
        reasons.append("selection_lock_before_evidence_missing")
    if not isinstance(lock_selection.get("prior_post_anchor_failures_reviewed"), list):
        reasons.append("selection_lock_prior_review_missing")

    if payload.get("outcome_at_selection") != "UNKNOWN":
        reasons.append("selection_lock_outcome_known")
    if payload.get("fix_commit_sha") is not None:
        reasons.append("selection_lock_fix_already_known")
    if payload.get("result_commit_sha") is not None:
        reasons.append("selection_lock_result_already_known")
    if payload.get("prospective_claim") is not False:
        reasons.append("selection_lock_prospective_claim_forbidden")
    if payload.get("blind_holdout_claim") is not False:
        reasons.append("selection_lock_blind_claim_forbidden")
    if payload.get("production_world_claim") is not False:
        reasons.append("selection_lock_production_claim_forbidden")

    return reasons


def _trial_from_mapping(value: Mapping[str, Any]) -> BenchmarkTrial:
    return BenchmarkTrial(
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


def load_prospective_result(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("prospective result must be a JSON object")
    return payload


def evaluate_prospective_result(
    value: Mapping[str, Any],
    *,
    repository_root: Path | str | None = None,
    trust_ancestry_flag: bool = False,
) -> dict[str, Any]:
    """Validate Phase-B governance and evaluate the fixed Tiny-to-Beast contract.

    Production callers must provide ``repository_root``.  The evaluator then
    reads the selection-lock artifact from the recorded selection commit and
    does not trust an embedded copy as authority. ``trust_ancestry_flag`` exists
    only for isolated unit testing, where a digest-valid embedded lock may stand
    in for committed Git evidence; it must never be enabled by CLI or CI.
    """

    payload = dict(value)
    reasons: list[str] = []

    if payload.get("schema_version") != "prospective-transfer-result-v1":
        reasons.append("unsupported_schema")
    if payload.get("registration_id") != REGISTRATION_ID:
        reasons.append("registration_id_mismatch")
    if payload.get("phase") != "RESULT":
        reasons.append("invalid_phase")
    if payload.get("preregistration_anchor_sha") != ANCHOR_SHA:
        reasons.append("preregistration_anchor_mismatch")
    if payload.get("preregistration_seal_sha256") != PREREGISTRATION_SEAL:
        reasons.append("preregistration_seal_mismatch")

    selection = payload.get("selection")
    if not isinstance(selection, Mapping):
        reasons.append("selection_missing")
        selection = {}
    if selection.get("first_eligible_confirmed") is not True:
        reasons.append("first_eligible_not_confirmed")
    if selection.get("naturally_occurring") is not True:
        reasons.append("natural_incident_not_confirmed")
    if selection.get("benchmark_authored") is not False:
        reasons.append("benchmark_authored_forbidden")
    if selection.get("intentionally_injected") is not False:
        reasons.append("intentional_injection_forbidden")
    if selection.get("documentation_only") is not False:
        reasons.append("documentation_only_forbidden")
    if selection.get("test_only_fixture") is not False:
        reasons.append("test_fixture_forbidden")
    if selection.get("same_origin_training") is not False:
        reasons.append("same_origin_training_forbidden")
    if selection.get("known_outcome_at_selection") is not False:
        reasons.append("outcome_known_at_selection")
    if selection.get("cherry_picked") is not False:
        reasons.append("cherry_pick_forbidden")

    chronology = payload.get("chronology")
    if not isinstance(chronology, Mapping):
        reasons.append("chronology_missing")
        chronology = {}
    chronology_keys = (
        "failure_commit_sha",
        "selection_lock_commit_sha",
        "fix_commit_sha",
        "result_commit_sha",
    )
    chronology_values = [str(chronology.get(key, "")) for key in chronology_keys]
    for key, sha in zip(chronology_keys, chronology_values):
        if not _SHA40.fullmatch(sha):
            reasons.append(f"invalid_{key}")

    selection_lock_path = _safe_repo_path(payload.get("selection_lock_path"))
    embedded_lock = payload.get("selection_lock_artifact")
    if selection_lock_path is None:
        reasons.append("selection_lock_binding_missing")

    selection_lock: dict[str, Any] | None = None
    if selection_lock_path is not None:
        if repository_root is not None and _SHA40.fullmatch(chronology_values[1]):
            selection_lock = _load_json_from_commit(
                Path(repository_root).resolve(),
                chronology_values[1],
                selection_lock_path,
            )
            if selection_lock is None:
                reasons.append("selection_lock_artifact_not_found_at_selection_commit")
        elif repository_root is None and trust_ancestry_flag:
            if isinstance(embedded_lock, Mapping):
                selection_lock = dict(embedded_lock)
            else:
                reasons.append("selection_lock_binding_missing")
        elif repository_root is None:
            reasons.append("selection_lock_artifact_not_verified")

    selection_lock_verified = False
    selection_lock_digest = ""
    selection_lock_lineage: dict[str, str] = {}
    if selection_lock is not None:
        lock_reasons = _selection_lock_reasons(
            selection_lock,
            expected_anchor_sha=ANCHOR_SHA,
            expected_failure_sha=chronology_values[0],
            result_selection=selection,
        )
        reasons.extend(lock_reasons)
        selection_lock_verified = not lock_reasons
        selection_lock_digest = str(selection_lock.get("selection_lock_digest_sha256") or "")
        selection_lock_lineage = {
            "candidate_digest_sha256": str(selection_lock.get("candidate_digest_sha256") or ""),
            "observation_digest_sha256": str(selection_lock.get("observation_digest_sha256") or ""),
            "eligibility_review_digest_sha256": str(
                selection_lock.get("eligibility_review_digest_sha256") or ""
            ),
            "eligibility_reviewer_id": str(selection_lock.get("eligibility_reviewer_id") or ""),
        }

    ancestry_verified = False
    if not any(reason.startswith("invalid_") and reason.endswith("_commit_sha") for reason in reasons):
        if repository_root is not None:
            ancestry_verified = verify_commit_order(
                repository_root,
                ANCHOR_SHA,
                *chronology_values,
            )
        elif trust_ancestry_flag:
            ancestry_verified = chronology.get("git_ancestry_verified") is True
    if not ancestry_verified:
        reasons.append("git_ancestry_not_verified")

    baseline: BenchmarkTrial | None = None
    learned: BenchmarkTrial | None = None
    try:
        baseline_value = payload.get("baseline")
        learned_value = payload.get("learned")
        if not isinstance(baseline_value, Mapping) or not isinstance(learned_value, Mapping):
            raise ValueError("baseline and learned mappings are required")
        baseline = _trial_from_mapping(baseline_value)
        learned = _trial_from_mapping(learned_value)
    except (KeyError, TypeError, ValueError):
        reasons.append("invalid_benchmark_trials")

    if baseline is not None and learned is not None:
        if baseline.family != FAMILY or learned.family != FAMILY:
            reasons.append("task_family_not_preregistered")
        if baseline.model_id != MODEL_ID or learned.model_id != MODEL_ID:
            reasons.append("model_not_preregistered")
        if baseline.hardware_id != HARDWARE_ID or learned.hardware_id != HARDWARE_ID:
            reasons.append("hardware_not_preregistered")
        if baseline.external_ai_used or learned.external_ai_used:
            reasons.append("sovereignty_contract_broken")

    valid_contract = not reasons
    growth_reasons: list[str] = []
    growth_payload: dict[str, Any] = {}
    growth_passed = False
    if baseline is not None and learned is not None:
        growth = evaluate_growth(
            baseline,
            learned,
            require_sovereign=True,
            minimum_transfer_distance=2,
        )
        growth_payload = growth.as_dict()
        growth_reasons.extend(growth.reasons)
        if growth.action_delta > -1:
            growth_reasons.append("minimum_action_improvement_not_met")
        if growth.intellectual_downshift < 1:
            growth_reasons.append("minimum_intellectual_downshift_not_met")
        growth_passed = not growth_reasons

    prospective_pass = valid_contract and growth_passed
    if not valid_contract:
        status = "INVALID_PROSPECTIVE_RESULT"
    elif prospective_pass:
        status = "PROSPECTIVE_TRANSFER_PASS"
    else:
        status = "PROSPECTIVE_TRANSFER_FAIL"

    return {
        "valid_contract": valid_contract,
        "status": status,
        "registration_id": str(payload.get("registration_id", "")),
        "preregistration_anchor_sha": str(payload.get("preregistration_anchor_sha", "")),
        "preregistration_seal_sha256": str(payload.get("preregistration_seal_sha256", "")),
        "git_ancestry_verified": ancestry_verified,
        "selection_lock_verified": selection_lock_verified,
        "selection_lock_path": selection_lock_path or "",
        "selection_lock_digest_sha256": selection_lock_digest,
        "selection_lock_lineage": selection_lock_lineage,
        "reasons": reasons,
        "growth": growth_payload,
        "growth_reasons": growth_reasons,
        "blind_holdout_claim": prospective_pass,
        "prospective_claim": prospective_pass,
        "production_world_claim": False,
    }
