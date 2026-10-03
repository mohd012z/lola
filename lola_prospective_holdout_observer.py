"""Observer-only watcher for LOLA's preregistered prospective holdout.

This module may record that an abnormal terminal workflow outcome happened
strictly after the sealed Phase-A anchor. It intentionally cannot decide
holdout eligibility, create a selection lock, repair a failure, or make any
prospective success claim. Selection-sensitive fields remain unknown until
independent review.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from lola_prospective_result import ANCHOR_SHA, PREREGISTRATION_SEAL, REGISTRATION_ID


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_REVIEWABLE_CONCLUSIONS = frozenset(
    {
        "failure",
        "timed_out",
        "startup_failure",
        "action_required",
        "cancelled",
    }
)
_REVIEW_FIELDS = (
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


def _strictly_after_anchor(repo: Path, anchor_sha: str, head_sha: str) -> bool:
    if not (_SHA40.fullmatch(anchor_sha) and _SHA40.fullmatch(head_sha)):
        return False
    if anchor_sha == head_sha:
        return False
    completed = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", anchor_sha, head_sha],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def _base(status: str) -> dict[str, Any]:
    return {
        "schema_version": "prospective-holdout-observation-v1",
        "registration_id": REGISTRATION_ID,
        "phase": "OBSERVER",
        "status": status,
        "preregistration_anchor_sha": ANCHOR_SHA,
        "preregistration_seal_sha256": PREREGISTRATION_SEAL,
        "observation_created": False,
        "selection_authorized": False,
        "lock_authorized": False,
        "automated_repair_authorized": False,
        "prospective_claim": False,
        "blind_holdout_claim": False,
        "production_world_claim": False,
    }


def observe_workflow_event(
    value: Mapping[str, Any],
    *,
    repository_root: Path | str,
    expected_anchor_sha: str = ANCHOR_SHA,
) -> dict[str, Any]:
    """Normalize one GitHub workflow_run event without selecting a holdout.

    A returned ``OBSERVED_REVIEW_REQUIRED`` object proves only two things:
    a watched workflow reached a reviewable abnormal terminal conclusion and
    its head commit is strictly after the preregistered anchor in the supplied
    local Git history. All semantic eligibility questions are deliberately
    left for independent review.
    """

    workflow_run = value.get("workflow_run") if isinstance(value, Mapping) else None
    if not isinstance(workflow_run, Mapping):
        result = _base("IGNORED_INVALID_EVENT")
        result["preregistration_anchor_sha"] = expected_anchor_sha
        result["reason"] = "workflow_run_missing"
        return result

    conclusion = str(workflow_run.get("conclusion") or "")
    head_sha = str(workflow_run.get("head_sha") or "")

    if conclusion not in _REVIEWABLE_CONCLUSIONS:
        result = _base("IGNORED_NOT_REVIEWABLE")
        result["preregistration_anchor_sha"] = expected_anchor_sha
        result["failure_commit_sha"] = head_sha
        result["git_ancestry_verified"] = False
        result["reason"] = "workflow_conclusion_not_reviewable"
        return result

    run_attempt = workflow_run.get("run_attempt")
    if isinstance(run_attempt, bool) or not isinstance(run_attempt, int) or run_attempt < 1:
        result = _base("IGNORED_INVALID_EVENT")
        result["preregistration_anchor_sha"] = expected_anchor_sha
        result["failure_commit_sha"] = head_sha
        result["git_ancestry_verified"] = False
        result["reason"] = "workflow_run_attempt_invalid"
        return result

    repo = Path(repository_root).resolve()
    ancestry_verified = _strictly_after_anchor(repo, expected_anchor_sha, head_sha)
    if not ancestry_verified:
        result = _base("IGNORED_NOT_POST_ANCHOR")
        result["preregistration_anchor_sha"] = expected_anchor_sha
        result["failure_commit_sha"] = head_sha
        result["git_ancestry_verified"] = False
        result["reason"] = "abnormal_outcome_not_strictly_after_anchor"
        return result

    run_id = workflow_run.get("id")
    run_url = str(workflow_run.get("html_url") or "")
    run_api_url = str(workflow_run.get("url") or "").strip()
    attempt_api_url = (
        f"{run_api_url.rstrip('/')}/attempts/{run_attempt}"
        if run_api_url
        else f"github-actions-run:{run_id}:attempt:{run_attempt}"
    )

    result: dict[str, Any] = _base("OBSERVED_REVIEW_REQUIRED")
    result.update(
        {
            "preregistration_anchor_sha": expected_anchor_sha,
            "observation_created": True,
            "failure_commit_sha": head_sha,
            "git_ancestry_verified": True,
            "source": "github_workflow_run",
            "workflow_run": {
                "id": run_id,
                "run_attempt": run_attempt,
                "name": str(workflow_run.get("name") or ""),
                "head_branch": str(workflow_run.get("head_branch") or ""),
                "trigger_event": str(workflow_run.get("event") or ""),
                "status": str(workflow_run.get("status") or ""),
                "conclusion": conclusion,
                "run_url": run_url,
                "run_api_url": run_api_url,
                "attempt_api_url": attempt_api_url,
                "run_started_at": workflow_run.get("run_started_at"),
                "updated_at": workflow_run.get("updated_at"),
            },
            "before_evidence_refs": [attempt_api_url],
            "review_fields": {field: None for field in _REVIEW_FIELDS},
            "repair_outcome": "UNKNOWN",
            "observer_boundary": (
                "Observation only: no holdout eligibility, first-eligible selection, "
                "selection lock, repair, or success claim is authorized."
            ),
        }
    )
    result["observation_digest_sha256"] = _canonical_digest(result)
    return result
