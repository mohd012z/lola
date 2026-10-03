"""Cognitive loop smoke — end-to-end offline exercise of the New LOLA pipeline.

docs/superpowers/specs/answer-planner-and-loop-smoke.md, Module M.

Follows the run_sovereign_smoke / run_tiny_beast_smoke convention: a
deterministic, offline, no-network/no-LLM check that every stage of the
pipeline behaves per its frozen invariants. Returns a dict with
"passed": bool and a "checks" list so the CLI/CI can surface exactly
which invariant broke.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def run_cognitive_loop_smoke() -> dict:
    from lola_fast_triage import fast_triage
    from lola_radar_scan import fast_radar, pass_b
    from lola_runtime_loop import run_loop, learning_governor
    from lola_evidence_bus import EvidenceBus, Finding
    from lola_answer_planner import plan_answer
    from lola_presentation import render_flow

    checks: list[dict] = []

    # 1. triage ANSWER route from verified state
    t_ans = fast_triage("what is the decoder buffer size",
                        verified_state={"decoder buffer size": "8192 bytes"})
    checks.append(_check("triage_answer_route",
                         t_ans.route == "ANSWER" and not t_ans.external_justified))

    # 2. triage MAP route when nothing closes the gap
    t_map = fast_triage("why does the application freeze only on android sixteen",
                        verified_state={}, inspectable=())
    checks.append(_check("triage_map_route", t_map.route == "MAP"
                         and not t_map.external_justified))

    # 3. radar pass_b is selective (skips GREEN + GREY)
    radar = fast_radar("python runtime decoder", known=("runtime",),
                       uncertain=("storage",))
    pb = pass_b(radar)
    checks.append(_check(
        "radar_pass_b_selective",
        "storage" in pb and "runtime" not in pb and "architecture" not in pb,
        f"pass_b={pb}"))

    # 4. clean freeze allows research
    r_clean = run_loop("why does it freeze",
                       verified_state={}, inspectable=(),
                       inventory={"known": (), "unknown": ("x",)},
                       frozen_idea={"frozen_before_external": True},
                       external_hits=("primary source says Y",))
    checks.append(_check("clean_freeze_allows_research",
                         not r_clean.quarantined
                         and r_clean.external_sources_used == 1))

    # 5. unfrozen + external hits -> quarantine + NOVELTY_BEFORE_EXTERNAL + REJECT
    r_quar = run_loop("why does it freeze",
                      verified_state={}, inspectable=(),
                      inventory={"known": (), "unknown": ("x",)},
                      frozen_idea={"frozen_before_external": False},
                      external_hits=("study says X",))
    checks.append(_check(
        "unfrozen_external_quarantined",
        r_quar.quarantined and "NOVELTY_BEFORE_EXTERNAL" in r_quar.violations
        and learning_governor(r_quar) == "REJECT"))

    # 6-9. answer planner types
    p_ts = plan_answer("why does the application freeze after ten seconds")
    p_re = plan_answer("research and compare the evidence for scheduling options")
    p_im = plan_answer("implement the new build pipeline and deploy it")
    p_ge = plan_answer("hello")
    checks.append(_check("planner_troubleshooting",
                         p_ts.question_type == "TROUBLESHOOTING"))
    checks.append(_check("planner_research",
                         p_re.question_type == "RESEARCH"))
    checks.append(_check("planner_implementation",
                         p_im.question_type == "IMPLEMENTATION"))
    checks.append(_check("planner_generic",
                         p_ge.question_type == "GENERIC"))

    # 10. /flow trace renders from a real report
    r_flow = run_loop("what is the decoder buffer size",
                      verified_state={"decoder buffer size": "8192 bytes"})
    flow = render_flow(r_flow.trace, task_id="smoke", external_ai_used=False,
                       evidence_count=len(r_flow.evidence_ids),
                       current_uncertainty="none")
    checks.append(_check("flow_trace_renders",
                         "TASK #smoke" in flow and "Intake" in flow))

    # 11. governor PROMOTE on a verified report with transfer+regression pass
    r_promote = replace(r_flow, transfer_passed=True, regression_passed=True)
    checks.append(_check("governor_promote_verified",
                         learning_governor(r_promote) == "PROMOTE"
                         and not r_promote.quarantined))

    # 12. evidence bus: agent count never votes
    bus = EvidenceBus()
    bus.register_evidence("e1", "e2")
    bus.submit(Finding("A", "X", ("e1",), (), ()))
    bus.submit(Finding("C", "X", ("e1",), (), ()))
    bus.submit(Finding("B", "Y", ("e2",), (), ("e1",)))
    winner, _, _ = bus.verdict("X", "Y")
    checks.append(_check("agent_count_does_not_vote", winner == "X"))

    passed = all(c["ok"] for c in checks)
    return {
        "passed": passed,
        "checks": checks,
        "pipeline": ("triage", "radar", "novelty", "research",
                     "evidence_bus", "planner", "presentation", "governor"),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run_cognitive_loop_smoke(), indent=2,
                     ensure_ascii=False, sort_keys=True))
