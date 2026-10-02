"""Public prospective-result gate with repair execution provenance enforced.

The original Phase-B evaluator is preserved verbatim in
``lola_prospective_result_legacy``. This module keeps its public surface while
adding the fail-closed execution-receipt boundary.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import lola_prospective_result_legacy as _legacy
from lola_prospective_execution_receipt import wrap_prospective_evaluator


# Preserve the complete legacy module surface, including private helpers used by
# focused tests, while keeping the new gate explicit at the public entry point.
for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)


_CONTRACT_GLOBALS = (
    "ANCHOR_SHA",
    "PREREGISTRATION_SEAL",
    "REGISTRATION_ID",
    "MODEL_ID",
    "HARDWARE_ID",
    "FAMILY",
)


def _sync_contract_globals() -> None:
    """Preserve patchability of contract constants across the compatibility split."""

    for name in _CONTRACT_GLOBALS:
        if name in globals():
            setattr(_legacy, name, globals()[name])


def _receipt_contract_required(
    value: Mapping[str, Any],
    *,
    repository_root: Path | str | None,
    trust_ancestry_flag: bool,
) -> bool:
    """Require receipts in production and in unit fixtures that opt into v1.

    ``trust_ancestry_flag`` is an isolated-test escape hatch inherited from the
    preregistered Phase-B evaluator and is never enabled by the CLI/CI path.
    Legacy synthetic unit fixtures may therefore keep testing their original
    boundary without being rewritten into execution-receipt fixtures. Any real
    repository evaluation, or any synthetic payload carrying receipt-contract
    fields, is governed by the new fail-closed receipt verifier.
    """

    if repository_root is not None or not trust_ancestry_flag:
        return True

    payload = dict(value)
    chronology = payload.get("chronology")
    if not isinstance(chronology, Mapping):
        chronology = {}
    authorization = payload.get("repair_authorization_artifact")
    if not isinstance(authorization, Mapping):
        authorization = {}
    evidence = payload.get("result_evidence_artifact")
    if not isinstance(evidence, Mapping):
        evidence = {}

    return any(
        (
            payload.get("execution_receipt_contract_required") is True,
            payload.get("repair_execution_receipt_path") is not None,
            isinstance(payload.get("repair_execution_receipt_artifact"), Mapping),
            chronology.get("repair_execution_receipt_commit_sha") is not None,
            authorization.get("authorized_executor_id") is not None,
            authorization.get("execution_nonce_sha256") is not None,
            authorization.get("single_use") is not None,
            authorization.get("execution_receipt_path") is not None,
            evidence.get("repair_execution_receipt_commit_sha") is not None,
            evidence.get("repair_execution_receipt_digest_sha256") is not None,
        )
    )


_wrapped_evaluator = wrap_prospective_evaluator(_legacy.evaluate_prospective_result)


def evaluate_prospective_result(
    value: Mapping[str, Any],
    *,
    repository_root: Path | str | None = None,
    trust_ancestry_flag: bool = False,
) -> dict[str, Any]:
    _sync_contract_globals()

    if not _receipt_contract_required(
        value,
        repository_root=repository_root,
        trust_ancestry_flag=trust_ancestry_flag,
    ):
        result = _legacy.evaluate_prospective_result(
            value,
            repository_root=repository_root,
            trust_ancestry_flag=trust_ancestry_flag,
        )
        result["repair_execution_receipt_verified"] = False
        result["repair_execution_receipt_path"] = ""
        result["repair_execution_receipt_digest_sha256"] = ""
        result["repair_execution_receipt_lineage"] = {}
        result["repair_fix_provenance_verified"] = False
        return result

    return _wrapped_evaluator(
        value,
        repository_root=repository_root,
        trust_ancestry_flag=trust_ancestry_flag,
    )
