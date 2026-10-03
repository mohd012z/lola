"""Execution-receipt authority for LOLA's prospective repair contract.

This module deliberately sits after repair authorization and before a prospective
result can count. Authorization says a repair may happen; the execution receipt
binds the governed result to the exact authorization and exact Git fix that was
actually produced. It does not itself claim the repair worked.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from functools import wraps
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_SCHEMA = "prospective-repair-execution-receipt-v1"


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


def _single_parent(repo: Path, commit_sha: str) -> str | None:
    if not _SHA40.fullmatch(commit_sha):
        return None
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--parents", "-n", "1", commit_sha],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    parts = completed.stdout.strip().split()
    if len(parts) != 2:
        return None
    return parts[1]


def _tree_sha(repo: Path, commit_sha: str) -> str | None:
    if not _SHA40.fullmatch(commit_sha):
        return None
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", f"{commit_sha}^{{tree}}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value if _SHA40.fullmatch(value) else None


def _patch_digest(repo: Path, parent_sha: str, fix_sha: str) -> tuple[str | None, bool]:
    if not (_SHA40.fullmatch(parent_sha) and _SHA40.fullmatch(fix_sha)):
        return None, False
    completed = subprocess.run(
        ["git", "-C", str(repo), "diff", "--binary", parent_sha, fix_sha],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return None, False
    return hashlib.sha256(completed.stdout).hexdigest(), bool(completed.stdout)


def _path_change_commits(repo: Path, start_sha: str, end_sha: str, path: str) -> list[str] | None:
    if not (_SHA40.fullmatch(start_sha) and _SHA40.fullmatch(end_sha)):
        return None
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "log",
            "--format=%H",
            "--reverse",
            f"{start_sha}..{end_sha}",
            "--",
            path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _authorization_consumption_reasons(
    authorization: Mapping[str, Any],
    *,
    expected_receipt_path: str,
) -> list[str]:
    reasons: list[str] = []
    executor_id = str(authorization.get("authorized_executor_id") or "").strip()
    if not executor_id:
        reasons.append("repair_authorization_executor_missing")
    nonce = str(authorization.get("execution_nonce_sha256") or "")
    if not _SHA256.fullmatch(nonce):
        reasons.append("repair_authorization_execution_nonce_invalid")
    if authorization.get("single_use") is not True:
        reasons.append("repair_authorization_not_single_use")
    if authorization.get("execution_receipt_path") != expected_receipt_path:
        reasons.append("repair_authorization_receipt_path_mismatch")
    return reasons


def _receipt_reasons(
    receipt: Mapping[str, Any],
    *,
    registration_id: str,
    anchor_sha: str,
    seal_sha256: str,
    failure_sha: str,
    selection_sha: str,
    selection_lock_digest: str,
    authorization_sha: str,
    authorization_digest: str,
    authorization: Mapping[str, Any],
    fix_sha: str,
) -> list[str]:
    reasons: list[str] = []
    payload = dict(receipt)

    if payload.get("schema_version") != _RECEIPT_SCHEMA:
        reasons.append("repair_execution_receipt_schema_invalid")
    if payload.get("registration_id") != registration_id:
        reasons.append("repair_execution_receipt_registration_mismatch")
    if payload.get("phase") != "REPAIR_EXECUTION_RECEIPT":
        reasons.append("repair_execution_receipt_phase_invalid")
    if payload.get("status") != "EXECUTED_AWAITING_RESULT":
        reasons.append("repair_execution_receipt_status_invalid")
    if payload.get("preregistration_anchor_sha") != anchor_sha:
        reasons.append("repair_execution_receipt_anchor_mismatch")
    if payload.get("preregistration_seal_sha256") != seal_sha256:
        reasons.append("repair_execution_receipt_seal_mismatch")
    if payload.get("failure_commit_sha") != failure_sha:
        reasons.append("repair_execution_receipt_failure_mismatch")
    if payload.get("selection_lock_commit_sha") != selection_sha:
        reasons.append("repair_execution_receipt_selection_commit_mismatch")
    if payload.get("selection_lock_digest_sha256") != selection_lock_digest:
        reasons.append("repair_execution_receipt_selection_lock_mismatch")
    if payload.get("repair_authorization_commit_sha") != authorization_sha:
        reasons.append("repair_execution_receipt_authorization_commit_mismatch")
    if payload.get("repair_authorization_digest_sha256") != authorization_digest:
        reasons.append("repair_execution_receipt_authorization_mismatch")

    if payload.get("authorized_executor_id") != authorization.get("authorized_executor_id"):
        reasons.append("repair_execution_receipt_executor_mismatch")
    if payload.get("execution_nonce_sha256") != authorization.get("execution_nonce_sha256"):
        reasons.append("repair_execution_receipt_nonce_mismatch")
    if payload.get("authorization_consumed") is not True:
        reasons.append("repair_execution_receipt_authorization_not_consumed")

    if payload.get("fix_commit_sha") != fix_sha:
        reasons.append("repair_execution_receipt_fix_mismatch")
    if payload.get("fix_parent_sha") != authorization_sha:
        reasons.append("repair_execution_receipt_fix_parent_mismatch")
    if not _SHA40.fullmatch(str(payload.get("fix_tree_sha") or "")):
        reasons.append("repair_execution_receipt_fix_tree_invalid")
    if not _SHA256.fullmatch(str(payload.get("fix_patch_sha256") or "")):
        reasons.append("repair_execution_receipt_fix_patch_invalid")

    supplied_digest = str(payload.get("repair_execution_receipt_digest_sha256") or "")
    if not _SHA256.fullmatch(supplied_digest):
        reasons.append("repair_execution_receipt_digest_missing_or_invalid")
    else:
        unsigned = dict(payload)
        unsigned.pop("repair_execution_receipt_digest_sha256", None)
        if _canonical_digest(unsigned) != supplied_digest:
            reasons.append("repair_execution_receipt_digest_mismatch")

    if payload.get("repair_outcome") != "UNKNOWN":
        reasons.append("repair_execution_receipt_outcome_known")
    if payload.get("result_commit_sha") is not None:
        reasons.append("repair_execution_receipt_result_already_known")
    if payload.get("prospective_claim") is not False:
        reasons.append("repair_execution_receipt_prospective_claim_forbidden")
    if payload.get("blind_holdout_claim") is not False:
        reasons.append("repair_execution_receipt_blind_claim_forbidden")
    if payload.get("production_world_claim") is not False:
        reasons.append("repair_execution_receipt_production_claim_forbidden")

    return reasons


def validate_execution_receipt(
    value: Mapping[str, Any],
    base_result: Mapping[str, Any],
    *,
    repository_root: Path | str | None = None,
    trust_ancestry_flag: bool = False,
) -> dict[str, Any]:
    payload = dict(value)
    reasons: list[str] = []
    chronology = payload.get("chronology")
    if not isinstance(chronology, Mapping):
        chronology = {}

    failure_sha = str(chronology.get("failure_commit_sha") or "")
    selection_sha = str(chronology.get("selection_lock_commit_sha") or "")
    authorization_sha = str(chronology.get("repair_authorization_commit_sha") or "")
    fix_sha = str(chronology.get("fix_commit_sha") or "")
    receipt_sha = str(chronology.get("repair_execution_receipt_commit_sha") or "")
    result_sha = str(chronology.get("result_commit_sha") or "")
    if not _SHA40.fullmatch(receipt_sha):
        reasons.append("invalid_repair_execution_receipt_commit_sha")

    receipt_path = _safe_repo_path(payload.get("repair_execution_receipt_path"))
    if receipt_path is None:
        reasons.append("repair_execution_receipt_binding_missing")
        receipt_path = ""

    authorization_path = _safe_repo_path(payload.get("repair_authorization_path"))
    result_evidence_path = _safe_repo_path(payload.get("result_evidence_path"))
    repo = Path(repository_root).resolve() if repository_root is not None else None

    authorization: dict[str, Any] | None = None
    if authorization_path is not None:
        if repo is not None:
            authorization = _load_json_from_commit(repo, authorization_sha, authorization_path)
        elif trust_ancestry_flag and isinstance(payload.get("repair_authorization_artifact"), Mapping):
            authorization = dict(payload["repair_authorization_artifact"])
    if authorization is None:
        reasons.append("repair_execution_receipt_authorization_not_available")
        authorization = {}

    if receipt_path:
        reasons.extend(
            _authorization_consumption_reasons(
                authorization,
                expected_receipt_path=receipt_path,
            )
        )

    receipt: dict[str, Any] | None = None
    if receipt_path:
        if repo is not None:
            receipt = _load_json_from_commit(repo, receipt_sha, receipt_path)
            if receipt is None:
                reasons.append("repair_execution_receipt_artifact_not_found_at_receipt_commit")
        elif trust_ancestry_flag and isinstance(
            payload.get("repair_execution_receipt_artifact"), Mapping
        ):
            receipt = dict(payload["repair_execution_receipt_artifact"])
        elif repo is None:
            reasons.append("repair_execution_receipt_artifact_not_verified")

    receipt_digest = ""
    receipt_lineage: dict[str, str] = {}
    if receipt is not None:
        receipt_reasons = _receipt_reasons(
            receipt,
            registration_id=str(payload.get("registration_id") or ""),
            anchor_sha=str(payload.get("preregistration_anchor_sha") or ""),
            seal_sha256=str(payload.get("preregistration_seal_sha256") or ""),
            failure_sha=failure_sha,
            selection_sha=selection_sha,
            selection_lock_digest=str(base_result.get("selection_lock_digest_sha256") or ""),
            authorization_sha=authorization_sha,
            authorization_digest=str(base_result.get("repair_authorization_digest_sha256") or ""),
            authorization=authorization,
            fix_sha=fix_sha,
        )
        reasons.extend(receipt_reasons)
        receipt_digest = str(receipt.get("repair_execution_receipt_digest_sha256") or "")
        receipt_lineage = {
            "repair_authorization_digest_sha256": str(
                receipt.get("repair_authorization_digest_sha256") or ""
            ),
            "execution_nonce_sha256": str(receipt.get("execution_nonce_sha256") or ""),
            "authorized_executor_id": str(receipt.get("authorized_executor_id") or ""),
            "fix_commit_sha": str(receipt.get("fix_commit_sha") or ""),
            "fix_tree_sha": str(receipt.get("fix_tree_sha") or ""),
            "fix_patch_sha256": str(receipt.get("fix_patch_sha256") or ""),
        }

    result_evidence: dict[str, Any] | None = None
    if result_evidence_path is not None:
        if repo is not None:
            result_evidence = _load_json_from_commit(repo, result_sha, result_evidence_path)
        elif trust_ancestry_flag and isinstance(payload.get("result_evidence_artifact"), Mapping):
            result_evidence = dict(payload["result_evidence_artifact"])
    if result_evidence is None:
        reasons.append("repair_execution_receipt_result_evidence_not_available")
    else:
        if result_evidence.get("repair_execution_receipt_commit_sha") != receipt_sha:
            reasons.append("result_evidence_execution_receipt_commit_mismatch")
        if result_evidence.get("repair_execution_receipt_digest_sha256") != receipt_digest:
            reasons.append("result_evidence_execution_receipt_digest_mismatch")

    git_provenance_verified = False
    if repo is not None and receipt is not None and receipt_path:
        fix_parent = _single_parent(repo, fix_sha)
        receipt_parent = _single_parent(repo, receipt_sha)
        result_parent = _single_parent(repo, result_sha)
        if fix_parent != authorization_sha:
            reasons.append("repair_execution_fix_not_direct_child_of_authorization")
        if receipt_parent != fix_sha:
            reasons.append("repair_execution_receipt_not_direct_child_of_fix")
        if result_parent != receipt_sha:
            reasons.append("prospective_result_not_direct_child_of_execution_receipt")

        actual_tree = _tree_sha(repo, fix_sha)
        if actual_tree != receipt.get("fix_tree_sha"):
            reasons.append("repair_execution_receipt_fix_tree_mismatch")
        patch_digest, has_patch = _patch_digest(repo, authorization_sha, fix_sha)
        if patch_digest != receipt.get("fix_patch_sha256"):
            reasons.append("repair_execution_receipt_fix_patch_mismatch")
        if not has_patch:
            reasons.append("repair_execution_receipt_empty_fix")

        if _load_json_from_commit(repo, authorization_sha, receipt_path) is not None:
            reasons.append("repair_execution_receipt_preexisted_authorization")
        changes = _path_change_commits(repo, authorization_sha, result_sha, receipt_path)
        if changes != [receipt_sha]:
            reasons.append("repair_execution_receipt_reused_or_mutated")

        git_provenance_verified = not any(
            reason
            for reason in reasons
            if reason.startswith("repair_execution_")
            or reason.startswith("prospective_result_not_direct_child")
        )
    elif trust_ancestry_flag and receipt is not None:
        git_provenance_verified = True

    verified = receipt is not None and not reasons
    return {
        "verified": verified,
        "path": receipt_path,
        "digest_sha256": receipt_digest,
        "lineage": receipt_lineage,
        "git_provenance_verified": git_provenance_verified,
        "reasons": reasons,
    }


def wrap_prospective_evaluator(
    base_evaluator: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    """Add fail-closed execution-receipt provenance to the existing result gate."""

    @wraps(base_evaluator)
    def wrapped(
        value: Mapping[str, Any],
        *,
        repository_root: Path | str | None = None,
        trust_ancestry_flag: bool = False,
    ) -> dict[str, Any]:
        result = base_evaluator(
            value,
            repository_root=repository_root,
            trust_ancestry_flag=trust_ancestry_flag,
        )
        receipt = validate_execution_receipt(
            value,
            result,
            repository_root=repository_root,
            trust_ancestry_flag=trust_ancestry_flag,
        )

        merged_reasons = list(result.get("reasons") or [])
        for reason in receipt["reasons"]:
            if reason not in merged_reasons:
                merged_reasons.append(reason)

        contract_valid = bool(result.get("valid_contract")) and receipt["verified"]
        result["reasons"] = merged_reasons
        result["valid_contract"] = contract_valid
        result["repair_execution_receipt_verified"] = receipt["verified"]
        result["repair_execution_receipt_path"] = receipt["path"]
        result["repair_execution_receipt_digest_sha256"] = receipt["digest_sha256"]
        result["repair_execution_receipt_lineage"] = receipt["lineage"]
        result["repair_fix_provenance_verified"] = receipt["git_provenance_verified"]

        if not contract_valid:
            result["status"] = "INVALID_PROSPECTIVE_RESULT"
            result["prospective_claim"] = False
            result["blind_holdout_claim"] = False
        return result

    return wrapped
