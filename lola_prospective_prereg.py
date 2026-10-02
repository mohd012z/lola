"""Sealed two-phase preregistration for prospective LOLA transfer evidence.

Phase A commits the hypothesis, evaluator identity, holdout-selection rule and
pass/fail contract before a future holdout exists.  A valid Phase-A document
must never claim prospective success; it can only report that the registration
is sealed and awaiting the first eligible post-merge defect.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
DEFAULT_PREREGISTRATION = ROOT / "fixtures" / "prospective_transfer_prereg_v1.json"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")


def compute_preregistration_seal(value: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop("seal_sha256", None)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_preregistration(path: Path | str = DEFAULT_PREREGISTRATION) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("preregistration document must be a JSON object")
    return payload


def validate_preregistration(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(value))
    reasons: list[str] = []

    if payload.get("schema_version") != "prospective-transfer-prereg-v1":
        reasons.append("unsupported_schema")
    if payload.get("phase") != "PREREGISTRATION":
        reasons.append("invalid_phase")
    if not payload.get("registration_id"):
        reasons.append("registration_id_missing")

    evidence = payload.get("evidence_base")
    if not isinstance(evidence, Mapping):
        reasons.append("evidence_base_missing")
        evidence = {}
    for key in ("base_commit_sha", "evaluator_blob_sha", "training_fixture_blob_sha"):
        if not _SHA40.fullmatch(str(evidence.get(key, ""))):
            reasons.append(f"invalid_{key}")

    selection = payload.get("holdout_selection")
    if not isinstance(selection, Mapping):
        reasons.append("holdout_selection_missing")
        selection = {}
    if selection.get("selection_mode") != "first_eligible_after_preregistration_merge":
        reasons.append("selection_mode_not_prospective")
    if selection.get("known_outcome_allowed") is not False:
        reasons.append("known_outcome_selection_forbidden")
    if selection.get("cherry_pick_allowed") is not False:
        reasons.append("cherry_pick_selection_forbidden")
    if selection.get("holdout_revealed") is not False:
        reasons.append("holdout_already_revealed_in_phase_a")
    if not selection.get("eligible_event"):
        reasons.append("eligible_event_missing")
    surfaces = selection.get("eligible_surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        reasons.append("eligible_surfaces_missing")

    contract = payload.get("evaluation_contract")
    if not isinstance(contract, Mapping):
        reasons.append("evaluation_contract_missing")
        contract = {}
    if int(contract.get("minimum_transfer_distance", -1)) < 2:
        reasons.append("transfer_distance_below_t2")
    if contract.get("same_model_required") is not True:
        reasons.append("same_model_not_required")
    if contract.get("same_hardware_required") is not True:
        reasons.append("same_hardware_not_required")
    if contract.get("sovereign_required") is not True:
        reasons.append("sovereignty_not_required")
    if contract.get("baseline_verified_required") is not True:
        reasons.append("baseline_verification_not_required")
    if contract.get("learned_verified_required") is not True:
        reasons.append("learned_verification_not_required")
    if int(contract.get("minimum_intellectual_downshift", 0)) < 1:
        reasons.append("intellectual_downshift_not_required")
    if int(contract.get("minimum_action_delta", 0)) >= 0:
        reasons.append("action_improvement_not_required")
    if int(contract.get("maximum_regression_failures", -1)) != 0:
        reasons.append("regressions_not_fail_closed")
    if contract.get("false_solved_allowed") is not False:
        reasons.append("false_solved_not_forbidden")
    if contract.get("evaluator_change_after_reveal_allowed") is not False:
        reasons.append("post_reveal_evaluator_change_allowed")
    if contract.get("hypothesis_change_after_reveal_allowed") is not False:
        reasons.append("post_reveal_hypothesis_change_allowed")

    ceiling = payload.get("claim_ceiling_before_reveal")
    if not isinstance(ceiling, Mapping):
        reasons.append("claim_ceiling_missing")
        ceiling = {}
    for claim in ("blind_holdout_claim", "prospective_claim", "production_world_claim"):
        if ceiling.get(claim) is not False:
            reasons.append(f"premature_{claim}")

    expected_seal = str(payload.get("seal_sha256", ""))
    computed_seal = compute_preregistration_seal(payload)
    seal_valid = bool(_SHA64.fullmatch(expected_seal) and expected_seal == computed_seal)
    if not seal_valid:
        reasons.insert(0, "contract_digest_mismatch")

    valid = not reasons
    status = "SEALED_AWAITING_HOLDOUT" if valid else (
        "INVALID_SEAL" if not seal_valid else "INVALID_CONTRACT"
    )
    return {
        "valid": valid,
        "status": status,
        "phase": str(payload.get("phase", "")),
        "registration_id": str(payload.get("registration_id", "")),
        "contract_digest": computed_seal,
        "sealed_digest": expected_seal,
        "hypothesis": str(evidence.get("hypothesis", "")),
        "base_commit_sha": str(evidence.get("base_commit_sha", "")),
        "evaluator_blob_sha": str(evidence.get("evaluator_blob_sha", "")),
        "training_fixture_blob_sha": str(evidence.get("training_fixture_blob_sha", "")),
        "model_id": str(evidence.get("model_id", "")),
        "hardware_id": str(evidence.get("hardware_id", "")),
        "holdout_revealed": bool(selection.get("holdout_revealed", False)),
        "selection_mode": str(selection.get("selection_mode", "")),
        "reasons": reasons,
        "blind_holdout_claim": False,
        "prospective_claim": False,
        "production_world_claim": False,
    }
