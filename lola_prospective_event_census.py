"""Deterministic evidence census for LOLA's prospective first-eligible rule.

The census is evidence-only. It cannot decide semantic eligibility, select a
holdout, authorize repair, or make a prospective claim. It proves which
reviewable GitHub Actions events existed through the candidate. Independent
rejection verdicts for earlier events remain separate review inputs so the
history census itself stays immutable/read-only.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from lola_prospective_result import ANCHOR_SHA, PREREGISTRATION_SEAL, REGISTRATION_ID

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVIEWABLE_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "startup_failure", "action_required", "cancelled"}
)
_WATCHED_WORKFLOWS = frozenset(
    {"Toolchain smoke check", "Lola Code Doctor", "Lola Bot Health"}
)


def _canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _event_key(event: Mapping[str, Any]) -> str | None:
    started = str(event.get("run_started_at") or "").strip()
    run_id = event.get("run_id")
    attempt = event.get("run_attempt")
    if not started:
        return None
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        return None
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        return None
    return f"{started}|{run_id:020d}|{attempt:06d}"


def _normalize_run(run: Mapping[str, Any]) -> dict[str, Any] | None:
    workflow_name = str(run.get("name") or "")
    if workflow_name not in _WATCHED_WORKFLOWS:
        return None
    conclusion = str(run.get("conclusion") or "")
    if conclusion not in _REVIEWABLE_CONCLUSIONS:
        return None
    run_id = run.get("id")
    attempt = run.get("run_attempt")
    started = str(run.get("run_started_at") or "").strip()
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise ValueError("workflow run id must be a positive integer")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("workflow run attempt must be a positive integer")
    if not started:
        raise ValueError("workflow run start time is required")
    head_sha = str(run.get("head_sha") or "")
    if not _SHA40.fullmatch(head_sha):
        raise ValueError("workflow run head sha must be 40 lowercase hex characters")
    run_api_url = str(run.get("url") or "").strip()
    if not run_api_url:
        raise ValueError("workflow run API URL is required")

    event = {
        "run_id": run_id,
        "run_attempt": attempt,
        "head_sha": head_sha,
        "workflow_name": workflow_name,
        "conclusion": conclusion,
        "run_started_at": started,
        "updated_at": run.get("updated_at"),
        "attempt_api_url": f"{run_api_url.rstrip('/')}/attempts/{attempt}",
    }
    key = _event_key(event)
    if key is None:
        raise ValueError("workflow run cannot be normalized")
    event["event_key"] = key
    return event


def build_event_census(
    workflow_runs: Iterable[Mapping[str, Any]],
    *,
    candidate_run_id: int,
    candidate_run_attempt: int,
    history_complete: bool,
) -> dict[str, Any]:
    """Build an immutable census from a complete read-only Actions history export."""

    if history_complete is not True:
        raise ValueError("workflow history must be complete through the candidate")
    if isinstance(candidate_run_id, bool) or not isinstance(candidate_run_id, int) or candidate_run_id < 1:
        raise ValueError("candidate run id must be a positive integer")
    if (
        isinstance(candidate_run_attempt, bool)
        or not isinstance(candidate_run_attempt, int)
        or candidate_run_attempt < 1
    ):
        raise ValueError("candidate run attempt must be a positive integer")

    events = []
    for run in workflow_runs:
        if not isinstance(run, Mapping):
            raise ValueError("workflow history entries must be objects")
        event = _normalize_run(run)
        if event is not None:
            events.append(event)
    events.sort(key=lambda item: item["event_key"])

    candidate = next(
        (
            item
            for item in events
            if item["run_id"] == candidate_run_id
            and item["run_attempt"] == candidate_run_attempt
        ),
        None,
    )
    if candidate is None:
        raise ValueError("candidate workflow attempt is absent from reviewable history")

    candidate_key = candidate["event_key"]
    events_through_candidate = [item for item in events if item["event_key"] <= candidate_key]
    census: dict[str, Any] = {
        "schema_version": "prospective-event-census-v1",
        "registration_id": REGISTRATION_ID,
        "preregistration_anchor_sha": ANCHOR_SHA,
        "preregistration_seal_sha256": PREREGISTRATION_SEAL,
        "source": "github_actions_history",
        "candidate_event_key": candidate_key,
        "ordered_events": events_through_candidate,
        "history_complete_through_candidate": True,
        "prospective_claim": False,
        "blind_holdout_claim": False,
        "production_world_claim": False,
    }
    census["event_census_digest_sha256"] = _canonical_digest(census)
    return census


def validate_event_census(
    census: Mapping[str, Any],
    observation: Mapping[str, Any],
    prior_event_verdicts: Any,
) -> dict[str, Any]:
    """Validate immutable history plus separate rejection verdict accounting."""

    payload = dict(census)
    obs = dict(observation)
    reasons: list[str] = []

    if payload.get("schema_version") != "prospective-event-census-v1":
        reasons.append("event_census_schema_invalid")
    if payload.get("registration_id") != REGISTRATION_ID:
        reasons.append("event_census_registration_mismatch")
    if payload.get("preregistration_anchor_sha") != ANCHOR_SHA:
        reasons.append("event_census_anchor_mismatch")
    if payload.get("preregistration_seal_sha256") != PREREGISTRATION_SEAL:
        reasons.append("event_census_seal_mismatch")
    if payload.get("source") != "github_actions_history":
        reasons.append("event_census_source_invalid")
    if payload.get("history_complete_through_candidate") is not True:
        reasons.append("event_census_history_incomplete")
    if "prior_event_verdicts" in payload:
        reasons.append("event_census_must_not_embed_review_verdicts")
    if payload.get("prospective_claim") is not False:
        reasons.append("event_census_prospective_claim_forbidden")
    if payload.get("blind_holdout_claim") is not False:
        reasons.append("event_census_blind_claim_forbidden")
    if payload.get("production_world_claim") is not False:
        reasons.append("event_census_production_claim_forbidden")

    supplied_digest = str(payload.get("event_census_digest_sha256") or "")
    if not _SHA256.fullmatch(supplied_digest):
        reasons.append("event_census_digest_missing_or_invalid")
    else:
        unsigned = dict(payload)
        unsigned.pop("event_census_digest_sha256", None)
        if _canonical_digest(unsigned) != supplied_digest:
            reasons.append("event_census_digest_mismatch")

    events_raw = payload.get("ordered_events")
    events = events_raw if isinstance(events_raw, list) else []
    if not events:
        reasons.append("event_census_events_missing")

    normalized: list[tuple[str, Mapping[str, Any]]] = []
    seen_keys: set[str] = set()
    for item in events:
        if not isinstance(item, Mapping):
            reasons.append("event_census_event_invalid")
            continue
        key = _event_key(item)
        if key is None or str(item.get("event_key") or "") != key:
            reasons.append("event_census_event_key_invalid")
            continue
        if key in seen_keys:
            reasons.append("event_census_duplicate_event")
            continue
        seen_keys.add(key)
        if not _SHA40.fullmatch(str(item.get("head_sha") or "")):
            reasons.append("event_census_head_sha_invalid")
        if str(item.get("workflow_name") or "") not in _WATCHED_WORKFLOWS:
            reasons.append("event_census_workflow_invalid")
        if str(item.get("conclusion") or "") not in _REVIEWABLE_CONCLUSIONS:
            reasons.append("event_census_conclusion_invalid")
        if not str(item.get("attempt_api_url") or "").strip():
            reasons.append("event_census_attempt_evidence_missing")
        normalized.append((key, item))

    keys = [key for key, _ in normalized]
    if keys != sorted(keys):
        reasons.append("event_census_order_invalid")

    candidate_key = str(payload.get("candidate_event_key") or "")
    event_map = {key: item for key, item in normalized}
    candidate_event = event_map.get(candidate_key)
    if candidate_event is None:
        reasons.append("event_census_candidate_missing")

    workflow_run = obs.get("workflow_run")
    if not isinstance(workflow_run, Mapping):
        reasons.append("event_census_observation_workflow_missing")
        workflow_run = {}

    if candidate_event is not None:
        expected = {
            "run_id": workflow_run.get("id"),
            "run_attempt": workflow_run.get("run_attempt"),
            "head_sha": obs.get("failure_commit_sha"),
            "workflow_name": workflow_run.get("name"),
            "conclusion": workflow_run.get("conclusion"),
            "run_started_at": workflow_run.get("run_started_at"),
            "updated_at": workflow_run.get("updated_at"),
            "attempt_api_url": workflow_run.get("attempt_api_url"),
        }
        for field, value in expected.items():
            if candidate_event.get(field) != value:
                reasons.append("event_census_candidate_observation_mismatch")
                break

    prior_keys = [key for key in keys if candidate_key and key < candidate_key]
    verdicts = prior_event_verdicts if isinstance(prior_event_verdicts, list) else []
    if not isinstance(prior_event_verdicts, list):
        reasons.append("event_census_prior_verdicts_missing")

    verdict_map: dict[str, Mapping[str, Any]] = {}
    for item in verdicts:
        if not isinstance(item, Mapping):
            reasons.append("event_census_prior_verdict_invalid")
            continue
        key = str(item.get("event_key") or "")
        if key in verdict_map:
            reasons.append("event_census_duplicate_prior_verdict")
            continue
        verdict_map[key] = item

    for key in prior_keys:
        verdict = verdict_map.get(key)
        if verdict is None:
            reasons.append("prior_event_unreviewed")
            continue
        if verdict.get("status") != "REVIEW_REJECTED":
            reasons.append("prior_event_not_rejected")
        if not _SHA256.fullmatch(str(verdict.get("eligibility_review_digest_sha256") or "")):
            reasons.append("prior_event_review_digest_invalid")

    if set(verdict_map) != set(prior_keys):
        if set(verdict_map) - set(prior_keys):
            reasons.append("event_census_prior_verdict_scope_invalid")

    valid = not reasons
    return {
        "valid": valid,
        "reasons": reasons,
        "event_census_digest_sha256": supplied_digest,
        "candidate_event_key": candidate_key,
        "prior_event_keys": prior_keys,
        "first_eligible_derived": valid,
    }
