"""Cognitive-loop runner — the New LOLA pipeline on real input.

docs/superpowers/specs/loop-runner-and-recheck-v1.md, Module Q.

The smoke test (#47) proves the pipeline behaves; this runner applies it
to actual input: a question (plus optional verified state, inspectables,
inventory, frozen idea, external hits, prediction/observation) becomes a
JSON-safe report with derived agent roles, the /flow trace, the learning
governor verdict, and — when the prediction is off — the named recheck
feedback edge. The runner decides WHAT and in what ORDER; executing the
roles is the caller's job.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Mapping

from lola_agent_roles import derive_roles
from lola_presentation import render_flow
from lola_recheck import recheck_cycle
from lola_runtime_loop import learning_governor, run_loop


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
    return str(value)


def run_cognitive_loop(input: Mapping[str, Any], *, task_id: str = "loop") -> dict:
    """Run the full pipeline on one real input; return a JSON-safe dict."""
    question = input.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("input must carry a non-empty 'question' string")

    report = run_loop(
        question,
        verified_state=input.get("verified_state") or {},
        inspectable=tuple(input.get("inspectable") or ()),
        inventory=input.get("inventory"),
        frozen_idea=input.get("frozen_idea"),
        external_hits=tuple(input.get("external_hits") or ()),
        prediction=input.get("prediction"),
        observed=input.get("observed"),
    )
    inventory = input.get("inventory") or {}
    unknowns = tuple(inventory.get("unknown") or ())
    roles = derive_roles(question, gap=unknowns)
    external_ai_used = report.external_sources_used > 0
    uncertainty = (unknowns[0] if unknowns else "none")
    flow = render_flow(
        report.trace,
        task_id=task_id,
        external_ai_used=external_ai_used,
        evidence_count=len(report.evidence_ids),
        current_uncertainty=uncertainty,
    )
    out = {
        "report": _jsonable(dataclasses.asdict(report)),
        "roles": list(roles),
        "flow": flow,
        "governor": learning_governor(report),
    }
    if report.needs_recheck and report.prediction_error is not None:
        # single observed delta -> the named feedback edge
        rc = recheck_cycle(expected_values=(0,),
                           observed_values=(report.prediction_error,))
        out["recheck"] = _jsonable(dataclasses.asdict(rc))
    return out
