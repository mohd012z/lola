"""Independent eligibility review for prospective LOLA holdout observations.

This module sits strictly between the read-only observer and the existing
selection-lock contract.  It can classify an observation as review-eligible
or review-rejected, but it cannot create a candidate, selection lock, repair,
or prospective success claim.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from lola_prospective_result import ANCHOR_SHA, PREREGISTRATION_SEAL, REGISTRATION_ID


_ALLOWED_SURFACES = {"source", "workflow", "config", "runtime-integration"}
_REQUIRED_REVIEW_FIELDS = (
    "surface",
    "naturally_occurring",
    "benchmark_authored",
    "intentionally_injected",
    "documentation_only",
    "test_only_fixture",
    "same_origin_training",
    "known_outcome_at_selection",
    "cherry_picked",
    "first_eligible_confirmed",
    "prior_post_anchor_failures_reviewed",
)


def _canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _observation_digest_valid(observation: Mapping[str, Any]) -> bool:
    supplied = str(observation.get("observation_digest_sha256") or "")
    if len(supplied) != 64:
        return False
    payload = dict(observation)
    payload.pop("observation_digest_sha256", None)
    return _canonical_digest(payload) == supplied


def review_observation(
    observation: Mapping[str, Any],
    review: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate an independent pre-repair eligibility review fail-closed."""

    obs = dict(observation)
    rv = dict(review)
    reasons: list[str] = []

    if obs.get("schema_version") != "prospective-holdout-observation-v1":
        reasons.append("unsupported_observation_schema")
    if obs.get("status") != "OBSERVED_REVIEW_REQUIRED":
        reasons.append("observation_not_reviewable")
    if obs.get("registration_id") != REGISTRATION_ID:
        reasons.append("observation_registration_mismatch")
    if obs.get("preregistration_anchor_sha") != ANCHOR_SHA:
        reasons.append("observation_anchor_mismatch")
    if obs.get("preregistration_seal_sha256") != PREREGISTRATION_SEAL:
        reasons.append("observation_seal_mismatch")
    if obs.get("git_ancestry_verified") is not True:
        reasons.append("observation_ancestry_not_verified")
    if obs.get("repair_outcome") != "UNKNOWN":
        reasons.append("repair_outcome_already_known")
    if obs.get("selection_authorized") is not False:
        reasons.append("observation_selection_boundary_broken")
    if obs.get("lock_authorized") is not False:
        reasons.append("observation_lock_boundary_broken")
    if obs.get("automated_repair_authorized") is not False:
        reasons.append("observation_repair_boundary_broken")
    if not _observation_digest_valid(obs):
        reasons.append("observation_digest_mismatch")

    if rv.get("schema_version") != "prospective-holdout-eligibility-review-v1":
        reasons.append("unsupported_review_schema")
    if rv.get("registration_id") != REGISTRATION_ID:
        reasons.append("review_registration_mismatch")
    if rv.get("observation_digest_sha256") != obs.get("observation_digest_sha256"):
        reasons.append("review_observation_digest_mismatch")

    reviewer_id = str(rv.get("reviewer_id") or "").strip()
    if not reviewer_id:
        reasons.append("reviewer_id_missing")
    if rv.get("reviewer_independent") is not True:
        reasons.append("reviewer_not_independent")
    if rv.get("review_completed_before_repair") is not True:
        reasons.append("review_not_completed_before_repair")

    fields = rv.get("review_fields")
    if not isinstance(fields, Mapping):
        reasons.append("review_fields_missing")
        fields = {}
    else:
        missing = [name for name in _REQUIRED_REVIEW_FIELDS if name not in fields]
        if missing:
            reasons.append("review_fields_incomplete")

    if fields.get("surface") not in _ALLOWED_SURFACES:
        reasons.append("ineligible_failure_surface")
    if fields.get("naturally_occurring") is not True:
        reasons.append("natural_incident_not_confirmed")
    if fields.get("benchmark_authored") is not False:
        reasons.append("benchmark_authored_forbidden")
    if fields.get("intentionally_injected") is not False:
        reasons.append("intentional_injection_forbidden")
    if fields.get("documentation_only") is not False:
        reasons.append("documentation_only_forbidden")
    if fields.get("test_only_fixture") is not False:
        reasons.append("test_fixture_forbidden")
    if fields.get("same_origin_training") is not False:
        reasons.append("same_origin_training_forbidden")
    if fields.get("known_outcome_at_selection") is not False:
        reasons.append("outcome_known_at_review")
    if fields.get("cherry_picked") is not False:
        reasons.append("cherry_pick_forbidden")
    if fields.get("first_eligible_confirmed") is not True:
        reasons.append("first_eligible_not_confirmed")
    if not isinstance(fields.get("prior_post_anchor_failures_reviewed"), list):
        reasons.append("prior_failure_review_missing")

    valid = not reasons
    result: dict[str, Any] = {
        "schema_version": "prospective-holdout-eligibility-verdict-v1",
        "registration_id": REGISTRATION_ID,
        "phase": "ELIGIBILITY_REVIEW",
        "status": "REVIEW_ELIGIBLE" if valid else "REVIEW_REJECTED",
        "valid_review": valid,
        "observation_digest_sha256": str(obs.get("observation_digest_sha256") or ""),
        "failure_commit_sha": str(obs.get("failure_commit_sha") or ""),
        "reviewer_id": reviewer_id,
        "reviewer_independent": rv.get("reviewer_independent") is True,
        "review_completed_before_repair": rv.get("review_completed_before_repair") is True,
        "review_fields": dict(fields),
        "reasons": reasons,
        "repair_outcome": "UNKNOWN",
        "candidate_authorized": False,
        "selection_authorized": False,
        "lock_authorized": False,
        "automated_repair_authorized": False,
        "prospective_claim": False,
        "blind_holdout_claim": False,
        "production_world_claim": False,
        "review_boundary": (
            "Eligibility classification only: candidate construction, selection lock, "
            "repair, and prospective success claims remain separate gated actions."
        ),
    }
    result["eligibility_review_digest_sha256"] = _canonical_digest(result)
    return result
