"""Full-chain smoke — the single cross-module proof the architecture holds.

The unit smokes (#47) and entry tests (#50) each prove one module. This
smoke asserts the CHAIN: raw human input -> gateway normalize -> default-
deny gate -> cognitive loop -> epistemic fuse, across modules, so CI
fails if any link is cut. It is the one test that exercises the whole
New LOLA stack end-to-end (HUMAN -> GATEWAY -> KIPEnvelope -> KERNEL ->
loop -> answer/fuse).

Deterministic, offline, no network/LLM. Follows the run_*_smoke
convention: returns {"passed": bool, "checks": [...], "chain": [...]}.
"""
from __future__ import annotations

from typing import Any

from lola_cognitive_entry import cognitive_entry
from lola_interaction_gateway import (
    ActorIdentity,
    TrustClass,
)

CHAIN_STAGES = ("normalize", "gate", "loop", "fuse")

_LOCAL = ActorIdentity(
    actor_id="fatah",
    trust_class=TrustClass.LOCAL_DEVICE,
    granted_scopes=frozenset({"cognitive_query"}),
)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _assert_no_cognition() -> dict:
    """Law 2, asserted directly: an unknown actor is denied and NO
    cognition runs (report/roles/flow/governor all None)."""
    out = cognitive_entry(
        "cli", "what is the decoder buffer size", _LOCAL,
        session_id="sess-chain", actors={},  # empty table -> UNKNOWN_ACTOR
        verified_state={"decoder buffer size": "8192 bytes"},
    )
    ok = (
        out.status == "DENIED"
        and out.report is None
        and out.roles is None
        and out.flow is None
        and out.governor is None
        and out.escalation is not None
    )
    return _check("default_deny_before_cognition", ok,
                  f"status={out.status} report={out.report}")


def run_full_chain_smoke() -> dict:
    checks: list[dict] = []
    traversed: list[str] = []

    # --- normalize + happy path (sovereign answer, no models) ---------
    happy = cognitive_entry(
        "cli", "what is the decoder buffer size", _LOCAL,
        session_id="sess-happy", actors={"fatah": _LOCAL},
        verified_state={"decoder buffer size": "8192 bytes"},
    )
    traversed += ["normalize", "gate", "loop"]
    checks.append(_check(
        "happy_path_sovereign_answer",
        happy.status == "ANSWERED"
        and happy.report is not None
        and happy.report["route"] == "ANSWER"
        and happy.report["confidence"] == "SUPPORTED",
        f"route={happy.report and happy.report['route']}"))
    # --- normalize: five-key provenance contract on the envelope ------
    from lola_interaction_gateway import normalize_user_input
    envelope = normalize_user_input(
        "cli", "what is the decoder buffer size", _LOCAL,
        session_id="sess-happy", capability="cognitive_query",
    )
    prov_keys = set(envelope.provenance.keys())
    ok_prov = prov_keys == {
        "actor_id", "session_id", "transport", "trust_class", "authority",
    }
    checks.append(_check("five_key_provenance_contract", ok_prov,
                         f"keys={sorted(prov_keys)}"))

    # --- Law 2: default-deny before cognition -------------------------
    checks.append(_assert_no_cognition())

    # --- Law 1 + novelty-before-external: clean freeze fuses PASS -----
    clean = cognitive_entry(
        "telegram", "why does it freeze", _LOCAL,
        session_id="sess-clean", actors={"fatah": _LOCAL},
        inventory={"known": (), "unknown": ("lifecycle",)},
        frozen_idea={"frozen_before_external": True},
        external_hits=("primary source says Y",),
    )
    traversed += ["fuse"]
    checks.append(_check(
        "novelty_before_external_fuse_pass",
        clean.status == "ANSWERED"
        and clean.fuse is not None
        and clean.fuse["result"] == "PASS"
        and not clean.report["quarantined"],
        f"fuse={clean.fuse}"))

    # --- unfrozen + external -> quarantine + fuse CUT -----------------
    cut = cognitive_entry(
        "cli", "why does it freeze", _LOCAL,
        session_id="sess-cut", actors={"fatah": _LOCAL},
        inventory={"known": (), "unknown": ("lifecycle",)},
        frozen_idea={"frozen_before_external": False},
        external_hits=("study says X",),
    )
    checks.append(_check(
        "unfrozen_external_fuse_cut",
        cut.report is not None
        and cut.report["quarantined"]
        and "NOVELTY_BEFORE_EXTERNAL" in cut.report["violations"]
        and cut.fuse is not None
        and cut.fuse["result"] == "CUT"
        and cut.governor == "REJECT",
        f"fuse={cut.fuse} governor={cut.governor}"))

    # --- prediction-error feedback edge closes in the chain -----------
    edge = cognitive_entry(
        "cli", "what is the decoder buffer size", _LOCAL,
        session_id="sess-edge", actors={"fatah": _LOCAL},
        verified_state={"decoder buffer size": "8192 bytes"},
        prediction=100, observed=8192,
    )
    checks.append(_check(
        "prediction_error_feedback_edge",
        edge.report is not None
        and edge.report["needs_recheck"]
        and edge.recheck is not None
        and "prediction error" in edge.recheck["root_cause_gap"],
        f"recheck={edge.recheck and edge.recheck.get('root_cause_gap')}"))

    # --- determinism: run the whole chain again, identical result -----
    again = run_full_chain_smoke_once_happy()
    checks.append(_check("chain_deterministic", again is not None))

    return {
        "passed": all(c["ok"] for c in checks),
        "checks": checks,
        "chain": traversed,
    }


def run_full_chain_smoke_once_happy() -> Any:
    """Re-run the happy path to confirm determinism (idempotent)."""
    a = cognitive_entry(
        "cli", "what is the decoder buffer size", _LOCAL,
        session_id="sess-d1", actors={"fatah": _LOCAL},
        verified_state={"decoder buffer size": "8192 bytes"},
    )
    b = cognitive_entry(
        "cli", "what is the decoder buffer size", _LOCAL,
        session_id="sess-d1", actors={"fatah": _LOCAL},
        verified_state={"decoder buffer size": "8192 bytes"},
    )
    # same session_id -> deterministic session handling; reports match
    if a.report != b.report or a.gate != b.gate:
        return None
    return True
