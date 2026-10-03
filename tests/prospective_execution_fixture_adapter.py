import copy
import hashlib
import json
from typing import Any, Mapping


RECEIPT_PATH = "evidence/prospective-repair-execution-receipt.json"
EXECUTOR_ID = "lola-repair-executor-v1"
EXECUTION_NONCE = "f" * 64
ISOLATED_RECEIPT_COMMIT = "8" * 40
ISOLATED_FIX_TREE = "6" * 40
ISOLATED_FIX_PATCH = "7" * 64


def _digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def upgrade_payload(value):
    """Upgrade legacy isolated valid-result fixtures to the receipt contract.

    This is test-fixture migration only. Production verification still requires
    the receipt to be committed at the recorded Git commit and independently
    verifies fix parent/tree/patch provenance.
    """

    payload = copy.deepcopy(value)
    chronology = payload.get("chronology")
    authorization = payload.get("repair_authorization_artifact")
    lock = payload.get("selection_lock_artifact")
    evidence = payload.get("result_evidence_artifact")
    if not all(
        isinstance(item, dict)
        for item in (chronology, authorization, lock, evidence)
    ):
        return payload

    authorization["authorized_executor_id"] = EXECUTOR_ID
    authorization["execution_nonce_sha256"] = EXECUTION_NONCE
    authorization["single_use"] = True
    authorization["execution_receipt_path"] = RECEIPT_PATH
    authorization.pop("repair_authorization_digest_sha256", None)
    authorization["repair_authorization_digest_sha256"] = _digest(authorization)

    failure_sha = str(chronology.get("failure_commit_sha") or "")
    selection_sha = str(chronology.get("selection_lock_commit_sha") or "")
    authorization_sha = str(chronology.get("repair_authorization_commit_sha") or "")
    fix_sha = str(chronology.get("fix_commit_sha") or "")
    receipt_sha = str(
        chronology.get("repair_execution_receipt_commit_sha")
        or ISOLATED_RECEIPT_COMMIT
    )
    chronology["repair_execution_receipt_commit_sha"] = receipt_sha

    receipt = {
        "schema_version": "prospective-repair-execution-receipt-v1",
        "registration_id": payload.get("registration_id"),
        "phase": "REPAIR_EXECUTION_RECEIPT",
        "status": "EXECUTED_AWAITING_RESULT",
        "preregistration_anchor_sha": payload.get("preregistration_anchor_sha"),
        "preregistration_seal_sha256": payload.get("preregistration_seal_sha256"),
        "failure_commit_sha": failure_sha,
        "selection_lock_commit_sha": selection_sha,
        "selection_lock_digest_sha256": lock.get("selection_lock_digest_sha256"),
        "repair_authorization_commit_sha": authorization_sha,
        "repair_authorization_digest_sha256": authorization[
            "repair_authorization_digest_sha256"
        ],
        "authorized_executor_id": EXECUTOR_ID,
        "execution_nonce_sha256": EXECUTION_NONCE,
        "authorization_consumed": True,
        "fix_commit_sha": fix_sha,
        "fix_parent_sha": authorization_sha,
        "fix_tree_sha": ISOLATED_FIX_TREE,
        "fix_patch_sha256": ISOLATED_FIX_PATCH,
        "repair_outcome": "UNKNOWN",
        "result_commit_sha": None,
        "prospective_claim": False,
        "blind_holdout_claim": False,
        "production_world_claim": False,
    }
    receipt["repair_execution_receipt_digest_sha256"] = _digest(receipt)

    payload["repair_execution_receipt_path"] = RECEIPT_PATH
    payload["repair_execution_receipt_artifact"] = receipt

    evidence["repair_authorization_digest_sha256"] = authorization[
        "repair_authorization_digest_sha256"
    ]
    evidence["repair_execution_receipt_commit_sha"] = receipt_sha
    evidence["repair_execution_receipt_digest_sha256"] = receipt[
        "repair_execution_receipt_digest_sha256"
    ]
    evidence.pop("result_evidence_digest_sha256", None)
    evidence["result_evidence_digest_sha256"] = _digest(evidence)

    return payload
