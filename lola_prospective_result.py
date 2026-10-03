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


_wrapped_evaluator = wrap_prospective_evaluator(_legacy.evaluate_prospective_result)


def evaluate_prospective_result(
    value: Mapping[str, Any],
    *,
    repository_root: Path | str | None = None,
    trust_ancestry_flag: bool = False,
) -> dict[str, Any]:
    _sync_contract_globals()
    return _wrapped_evaluator(
        value,
        repository_root=repository_root,
        trust_ancestry_flag=trust_ancestry_flag,
    )
