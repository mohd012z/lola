"""Construct a prospective holdout candidate from independently reviewed evidence.

This module bridges an observer artifact plus a REVIEW_ELIGIBLE verdict into the
existing candidate schema consumed by the separate selection-lock gate.  It
cannot create a selection lock, repair a failure, or make a prospective claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from lola_prospective_result import ANCHOR_SHA, PREREGISTRATION_SEAL, REGISTRATION_ID


def _canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _digest_valid(value: Mapping[str, Any], field: str) -> bool:
    supplied = str(value.get(field) or "")
    if len(supplied) != 64:
        return False
    payload = dict(value)
    payload.pop(field, None)
    return _canonical_digest(payload) == supplied


def build_candidate(
    observation: Mapping[str, Any],
    verdict: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a fail-closed pre-lock candidate from reviewed observation evidence."""

    obs = dict(observation)
    rv = dict(verdict)
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
    if not _digest_valid(obs, "observation_digest_sha256"):
        reasons.append("observation_digest_mismatch")

    if rv.get("schema_version") != "prospective-holdout-eligibility-verdict-v1":
        reasons.append("unsupported_review_schema")
    if rv.get("status") != "REVIEW_ELIGIBLE":
        reasons.append("review_not_eligible")
    if rv.get("valid_review") is not True:
        reasons.append("review_not_valid")
    if rv.get("registration_id") != REGISTRATION_ID:
        reasons.append("review_registration_mismatch")
    if rv.get("observation_digest_sha256") != obs.get("observation_digest_sha256"):
        reasons.append("review_observation_digest_mismatch")
    if rv.get("failure_commit_sha") != obs.get("failure_commit_sha"):
        reasons.append("failure_commit_mismatch")
    if rv.get("reviewer_independent") is not True:
        reasons.append("reviewer_not_independent")
    if rv.get("review_completed_before_repair") is not True:
        reasons.append("review_not_completed_before_repair")
    if rv.get("repair_outcome") != "UNKNOWN":
        reasons.append("review_repair_outcome_known")
    if rv.get("candidate_authorized") is not False:
        reasons.append("review_candidate_boundary_broken")
    if rv.get("selection_authorized") is not False:
        reasons.append("review_selection_boundary_broken")
    if rv.get("lock_authorized") is not False:
        reasons.append("review_lock_boundary_broken")
    if rv.get("automated_repair_authorized") is not False:
        reasons.append("review_repair_boundary_broken")
    if not _digest_valid(rv, "eligibility_review_digest_sha256"):
        reasons.append("eligibility_review_digest_mismatch")

    fields = rv.get("review_fields")
    if not isinstance(fields, Mapping):
        reasons.append("review_fields_missing")
        fields = {}

    before_refs = obs.get("before_evidence_refs")
    if (
        not isinstance(before_refs, list)
        or not before_refs
        or not all(isinstance(item, str) and item.strip() for item in before_refs)
    ):
        reasons.append("before_evidence_missing")

    if reasons:
        raise ValueError("invalid prospective candidate inputs: " + ",".join(reasons))

    candidate: dict[str, Any] = {
        "schema_version": "prospective-holdout-candidate-v1",
        "registration_id": REGISTRATION_ID,
        "phase": "CANDIDATE_CONSTRUCTION",
        "status": "CANDIDATE_READY_FOR_SELECTION_LOCK_REVIEW",
        "preregistration_anchor_sha": ANCHOR_SHA,
        "preregistration_seal_sha256": PREREGISTRATION_SEAL,
        "failure_commit_sha": str(obs["failure_commit_sha"]),
        "observation_digest_sha256": str(obs["observation_digest_sha256"]),
        "eligibility_review_digest_sha256": str(rv["eligibility_review_digest_sha256"]),
        "reviewer_id": str(rv.get("reviewer_id") or ""),
        "observed_failure": {
            "surface": fields.get("surface"),
            "observable_failure": True,
            "naturally_occurring": fields.get("naturally_occurring"),
            "benchmark_authored": fields.get("benchmark_authored"),
            "intentionally_injected": fields.get("intentionally_injected"),
            "documentation_only": fields.get("documentation_only"),
            "test_only_fixture": fields.get("test_only_fixture"),
            "same_origin_training": fields.get("same_origin_training"),
            "known_outcome_at_selection": fields.get("known_outcome_at_selection"),
            "cherry_picked": fields.get("cherry_picked"),
            "first_eligible_confirmed": fields.get("first_eligible_confirmed"),
            "before_evidence_refs": list(before_refs),
            "prior_post_anchor_failures_reviewed": list(
                fields.get("prior_post_anchor_failures_reviewed") or []
            ),
        },
        "candidate_constructed": True,
        "selection_authorized": False,
        "lock_authorized": False,
        "automated_repair_authorized": False,
        "repair_outcome": "UNKNOWN",
        "fix_commit_sha": None,
        "result_commit_sha": None,
        "prospective_claim": False,
        "blind_holdout_claim": False,
        "production_world_claim": False,
        "candidate_boundary": (
            "Candidate construction only: selection lock, repair, and prospective "
            "success claims require separate later gates."
        ),
    }
    candidate["candidate_digest_sha256"] = _canonical_digest(candidate)
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a reviewed prospective holdout candidate without locking or repair."
    )
    parser.add_argument("observation", help="Observer JSON artifact.")
    parser.add_argument("verdict", help="Independent eligibility verdict JSON artifact.")
    parser.add_argument("--output", required=True, help="Candidate JSON output path.")
    args = parser.parse_args()

    observation = json.loads(Path(args.observation).read_text(encoding="utf-8"))
    verdict = json.loads(Path(args.verdict).read_text(encoding="utf-8"))
    try:
        candidate = build_candidate(observation, verdict)
    except (TypeError, ValueError) as exc:
        print(json.dumps({"status": "CANDIDATE_REJECTED", "reason": str(exc)}, sort_keys=True))
        return 2

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(candidate, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(candidate, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
