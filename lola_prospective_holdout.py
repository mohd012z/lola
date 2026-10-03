"""Fail-closed selection lock for LOLA's preregistered prospective holdout.

This module governs the moment *before* repair.  It can freeze a qualifying
natural failure and its before-evidence, but it cannot record a repair outcome
or make any prospective/blind success claim.

Selection-lock v2 also requires the candidate-construction lineage introduced
after independent eligibility review.  A legacy/hand-crafted candidate that
bypasses observation/review/candidate digest binding is rejected.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from lola_prospective_result import (
    ANCHOR_SHA,
    PREREGISTRATION_SEAL,
    REGISTRATION_ID,
)


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


def _canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _candidate_digest_state(payload: Mapping[str, Any]) -> tuple[bool, str | None]:
    supplied = str(payload.get("candidate_digest_sha256") or "")
    if not _SHA256.fullmatch(supplied):
        return False, "candidate_digest_missing_or_invalid"
    unsigned = dict(payload)
    unsigned.pop("candidate_digest_sha256", None)
    if _canonical_digest(unsigned) != supplied:
        return False, "candidate_digest_mismatch"
    return True, None


def validate_holdout_candidate(
    value: Mapping[str, Any],
    *,
    repository_root: Path | str | None = None,
    expected_anchor_sha: str = ANCHOR_SHA,
    trust_ancestry_flag: bool = False,
) -> dict[str, Any]:
    """Validate a reviewed pre-repair candidate against the sealed selection rule."""

    payload = dict(value)
    reasons: list[str] = []

    if payload.get("schema_version") != "prospective-holdout-candidate-v1":
        reasons.append("unsupported_schema")
    if payload.get("registration_id") != REGISTRATION_ID:
        reasons.append("registration_id_mismatch")
    if payload.get("phase") != "CANDIDATE_CONSTRUCTION":
        reasons.append("candidate_phase_invalid")
    if payload.get("status") != "CANDIDATE_READY_FOR_SELECTION_LOCK_REVIEW":
        reasons.append("candidate_status_invalid")
    if payload.get("preregistration_anchor_sha") != expected_anchor_sha:
        reasons.append("preregistration_anchor_mismatch")
    if payload.get("preregistration_seal_sha256") != PREREGISTRATION_SEAL:
        reasons.append("preregistration_seal_mismatch")

    candidate_digest_verified, candidate_digest_reason = _candidate_digest_state(payload)
    if candidate_digest_reason:
        reasons.append(candidate_digest_reason)

    observation_digest = str(payload.get("observation_digest_sha256") or "")
    if not _SHA256.fullmatch(observation_digest):
        reasons.append("observation_digest_missing_or_invalid")
    review_digest = str(payload.get("eligibility_review_digest_sha256") or "")
    if not _SHA256.fullmatch(review_digest):
        reasons.append("eligibility_review_digest_missing_or_invalid")
    reviewer_id = str(payload.get("reviewer_id") or "").strip()
    if not reviewer_id:
        reasons.append("eligibility_reviewer_missing")

    if payload.get("candidate_constructed") is not True:
        reasons.append("candidate_construction_not_confirmed")
    if payload.get("selection_authorized") is not False:
        reasons.append("candidate_selection_boundary_broken")
    if payload.get("lock_authorized") is not False:
        reasons.append("candidate_lock_boundary_broken")
    if payload.get("automated_repair_authorized") is not False:
        reasons.append("candidate_repair_boundary_broken")
    if payload.get("repair_outcome") != "UNKNOWN":
        reasons.append("candidate_repair_outcome_known")
    if payload.get("fix_commit_sha") is not None:
        reasons.append("candidate_fix_already_known")
    if payload.get("result_commit_sha") is not None:
        reasons.append("candidate_result_already_known")
    if payload.get("prospective_claim") is not False:
        reasons.append("candidate_prospective_claim_forbidden")
    if payload.get("blind_holdout_claim") is not False:
        reasons.append("candidate_blind_claim_forbidden")
    if payload.get("production_world_claim") is not False:
        reasons.append("candidate_production_claim_forbidden")

    failure_sha = str(payload.get("failure_commit_sha", ""))
    if not _SHA40.fullmatch(failure_sha):
        reasons.append("invalid_failure_commit_sha")

    observed = payload.get("observed_failure")
    if not isinstance(observed, Mapping):
        reasons.append("observed_failure_missing")
        observed = {}

    if observed.get("surface") not in _ALLOWED_SURFACES:
        reasons.append("ineligible_failure_surface")
    if observed.get("observable_failure") is not True:
        reasons.append("observable_failure_not_confirmed")
    if observed.get("naturally_occurring") is not True:
        reasons.append("natural_incident_not_confirmed")
    if observed.get("benchmark_authored") is not False:
        reasons.append("benchmark_authored_forbidden")
    if observed.get("intentionally_injected") is not False:
        reasons.append("intentional_injection_forbidden")
    if observed.get("documentation_only") is not False:
        reasons.append("documentation_only_forbidden")
    if observed.get("test_only_fixture") is not False:
        reasons.append("test_fixture_forbidden")
    if observed.get("same_origin_training") is not False:
        reasons.append("same_origin_training_forbidden")
    if observed.get("known_outcome_at_selection") is not False:
        reasons.append("outcome_known_at_selection")
    if observed.get("cherry_picked") is not False:
        reasons.append("cherry_pick_forbidden")
    if observed.get("first_eligible_confirmed") is not True:
        reasons.append("first_eligible_not_confirmed")

    evidence_refs = observed.get("before_evidence_refs")
    if (
        not isinstance(evidence_refs, list)
        or not evidence_refs
        or not all(isinstance(item, str) and item.strip() for item in evidence_refs)
    ):
        reasons.append("before_evidence_missing")

    reviewed = observed.get("prior_post_anchor_failures_reviewed")
    if not isinstance(reviewed, list):
        reasons.append("prior_failure_review_missing")

    ancestry_verified = False
    if _SHA40.fullmatch(failure_sha):
        if failure_sha == expected_anchor_sha:
            reasons.append("failure_not_after_anchor")
        elif repository_root is not None:
            ancestry_verified = _git_is_ancestor(
                Path(repository_root).resolve(),
                expected_anchor_sha,
                failure_sha,
            )
            if not ancestry_verified:
                reasons.append("failure_not_after_anchor")
        elif trust_ancestry_flag:
            ancestry_verified = True
        else:
            reasons.append("git_ancestry_not_verified")

    valid = not reasons
    return {
        "valid_candidate": valid,
        "status": "ELIGIBLE_HOLDOUT_CANDIDATE" if valid else "REJECTED_HOLDOUT_CANDIDATE",
        "registration_id": str(payload.get("registration_id", "")),
        "preregistration_anchor_sha": str(payload.get("preregistration_anchor_sha", "")),
        "preregistration_seal_sha256": str(payload.get("preregistration_seal_sha256", "")),
        "failure_commit_sha": failure_sha,
        "git_ancestry_verified": ancestry_verified,
        "candidate_digest_verified": candidate_digest_verified,
        "candidate_digest_sha256": str(payload.get("candidate_digest_sha256") or ""),
        "observation_digest_sha256": observation_digest,
        "eligibility_review_digest_sha256": review_digest,
        "eligibility_reviewer_id": reviewer_id,
        "reasons": reasons,
        "prospective_claim": False,
        "blind_holdout_claim": False,
        "production_world_claim": False,
    }


def build_selection_lock(
    value: Mapping[str, Any],
    *,
    repository_root: Path | str | None = None,
    expected_anchor_sha: str = ANCHOR_SHA,
    trust_ancestry_flag: bool = False,
) -> dict[str, Any]:
    """Create a deterministic lock while preserving reviewed candidate lineage."""

    verdict = validate_holdout_candidate(
        value,
        repository_root=repository_root,
        expected_anchor_sha=expected_anchor_sha,
        trust_ancestry_flag=trust_ancestry_flag,
    )
    if not verdict["valid_candidate"]:
        raise ValueError("invalid prospective holdout candidate: " + ",".join(verdict["reasons"]))

    observed = dict(value["observed_failure"])
    lock: dict[str, Any] = {
        "schema_version": "prospective-holdout-selection-lock-v1",
        "registration_id": REGISTRATION_ID,
        "phase": "SELECTION_LOCK",
        "status": "LOCKED_AWAITING_REPAIR",
        "preregistration_anchor_sha": expected_anchor_sha,
        "preregistration_seal_sha256": PREREGISTRATION_SEAL,
        "failure_commit_sha": str(value["failure_commit_sha"]),
        "candidate_digest_sha256": str(value["candidate_digest_sha256"]),
        "observation_digest_sha256": str(value["observation_digest_sha256"]),
        "eligibility_review_digest_sha256": str(value["eligibility_review_digest_sha256"]),
        "eligibility_reviewer_id": str(value["reviewer_id"]),
        "selection": {
            "first_eligible_confirmed": True,
            "naturally_occurring": True,
            "benchmark_authored": False,
            "intentionally_injected": False,
            "documentation_only": False,
            "test_only_fixture": False,
            "same_origin_training": False,
            "known_outcome_at_selection": False,
            "cherry_picked": False,
            "surface": observed["surface"],
            "before_evidence_refs": list(observed["before_evidence_refs"]),
            "prior_post_anchor_failures_reviewed": list(observed["prior_post_anchor_failures_reviewed"]),
        },
        "outcome_at_selection": "UNKNOWN",
        "fix_commit_sha": None,
        "result_commit_sha": None,
        "prospective_claim": False,
        "blind_holdout_claim": False,
        "production_world_claim": False,
    }
    lock["selection_lock_digest_sha256"] = _canonical_digest(lock)
    return lock
