"""Stack verification — re-prove the whole New LOLA chain imports + works.

docs/superpowers/specs/delta-observe-and-stack-verify.md, Module T.

Post-merge deliverable: the single "the chain holds together" re-check.
Imports every New LOLA module (the #42-#52 set), runs the full-chain
smoke (#51), and runs a delta-observe cycle (#52). Returns per-module
import status + per-stage ok flags + overall passed. Runnable on the
stack branch and, post-merge, on main.
"""
from __future__ import annotations

import importlib

# The New LOLA module set, in dependency-light order.
_MODULES = (
    "lola_delta_memory", "lola_reasoning_layout",
    "lola_interaction_gateway", "lola_epistemic_fuse",
    "lola_novelty", "lola_cognition_ladder", "lola_learning_gate",
    "lola_radar_scan", "lola_parallelism_planner", "lola_cognitive_budget",
    "lola_presentation",
    "lola_fast_triage", "lola_research_stages", "lola_evidence_bus",
    "lola_runtime_loop", "lola_answer_planner", "lola_agent_roles",
    "lola_observe", "lola_recheck", "lola_cognitive_loop",
    "lola_cognitive_entry", "lola_full_chain_smoke",
    "lola_delta_observe",
    "lola_code_intel",
    "lola_candidate",
    "lola_causal_codegraph",
    "lola_concurrent_learning",
    "lola_lks",
)


def _import_ok(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def _full_chain_ok() -> bool:
    try:
        from lola_full_chain_smoke import run_full_chain_smoke
        return bool(run_full_chain_smoke()["passed"])
    except Exception:
        return False


def _delta_observe_ok() -> bool:
    try:
        from lola_delta_observe import PredictionErrorStore, run_recheck
        res = run_recheck(PredictionErrorStore(), [100, 100, 100])
        return (
            len(res["cycles"]) == 3
            and abs(res["cycles"][0]["prediction_error"] - 100.0) < 1e-9
            and res["converged_prediction"] > 0.0
        )
    except Exception:
        return False


def _code_intel_ok() -> bool:
    try:
        from lola_code_intel import run_code_intel_smoke
        return bool(run_code_intel_smoke()["passed"])
    except Exception:
        return False


def _candidate_ok() -> bool:
    try:
        from lola_candidate import run_candidate_smoke
        return bool(run_candidate_smoke()["passed"])
    except Exception:
        return False


def _causal_graph_ok() -> bool:
    try:
        from lola_causal_codegraph import run_causal_codegraph_smoke
        return bool(run_causal_codegraph_smoke()["passed"])
    except Exception:
        return False


def _concurrent_learning_ok() -> bool:
    try:
        from lola_concurrent_learning import run_concurrent_learning_smoke
        return bool(run_concurrent_learning_smoke()["passed"])
    except Exception:
        return False


def _lks_ok() -> bool:
    try:
        from lola_lks import run_lks_smoke
        return bool(run_lks_smoke()["passed"])
    except Exception:
        return False


def verify_merged_stack() -> dict:
    modules = {name: _import_ok(name) for name in _MODULES}
    stages = {
        "full_chain_smoke": _full_chain_ok(),
        "delta_observe": _delta_observe_ok(),
        "code_intel": _code_intel_ok(),
        "candidate": _candidate_ok(),
        "causal_graph": _causal_graph_ok(),
        "concurrent_learning": _concurrent_learning_ok(),
        "lks": _lks_ok(),
    }
    passed = all(modules.values()) and all(stages.values())
    return {
        "passed": passed,
        "modules": modules,
        "stages": stages,
        "module_count": len(modules),
        "missing_modules": sorted(n for n, ok in modules.items() if not ok),
        "failed_stages": sorted(s for s, ok in stages.items() if not ok),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(verify_merged_stack(), indent=2,
                     ensure_ascii=False, sort_keys=True))
