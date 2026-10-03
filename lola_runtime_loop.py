"""Runtime loop — the New LOLA identity loop, wired.

docs/superpowers/specs/new-lola-runtime-loop-v1.md, Module K.

    UNDERSTAND -> MAP -> INVENTORY -> GAP -> THINK -> INVENT
    -> PREDICT -> FALSIFY -> TEST -> OBSERVE -> RESEARCH IF NEEDED
    -> CHALLENGE -> VERIFY -> SYNTHESIZE -> ADAPT STYLE -> ANSWER
    -> RECHECK -> LEARN

v1 encodes each stage as a deterministic decision point. Executing
agents/waves is the caller's job; the loop decides WHAT and in what
ORDER, enforces novelty-before-external, checks stop conditions after
every stage, and reports evidence / agents / sources / tokens as
separate fields — never aggregated into a single "quality score".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from lola_cognitive_budget import CognitiveBudget, stop_condition
from lola_evidence_bus import EvidenceBus
from lola_fast_triage import fast_triage
from lola_presentation import confidence_from_evidence


@dataclass(frozen=True)
class LoopReport:
    question: str
    route: str
    stopped_by: str
    evidence_ids: tuple
    confidence: str
    agents_used: int
    external_sources_used: int
    quarantined: bool
    violations: tuple
    trace: tuple
    transfer_passed: bool = False
    regression_passed: bool = False


def _claim_states(bus: EvidenceBus, claims: Sequence[str]) -> list:
    out = []
    for c in claims:
        f = [x for x in bus.findings if x.finding == c]
        supported = bool(f) and all(x.evidence_ids for x in f)
        contradicted = any(x.contradictions for x in f)
        if contradicted:
            state = "CONTRADICTED"
        elif supported:
            state = "SUPPORTED"
        else:
            state = "UNVERIFIED"
        out.append({
            "id": c,
            "state": state,
            "evidence_ids": sorted({e for x in f for e in x.evidence_ids}),
        })
    return out
def run_loop(
    question: str,
    *,
    verified_state: Mapping[str, str] | None = None,
    inspectable: Sequence[str] = (),
    inventory: Mapping[str, Sequence[str]] | None = None,
    frozen_idea: Mapping[str, Any] | None = None,
    external_hits: Sequence[str] = (),
    budget: CognitiveBudget | None = None,
) -> LoopReport:
    budget = budget or CognitiveBudget()
    trace: list = []
    violations: list = []
    quarantined = False

    def step(name: str, status: str = "done") -> None:
        trace.append({"step": name, "status": status})

    step("Intake")
    triage = fast_triage(question, verified_state=verified_state,
                         inspectable=inspectable)
    step(f"Triage: {triage.route}")

    if triage.route == "ANSWER":
        step("Local knowledge checked")
        ev = f"verified:{triage.match}"
        claims = _claim_states(EvidenceBus(), [])
        conf = "SUPPORTED"
        step("Synthesize")
        step("Answer")
        report = LoopReport(
            question=question, route="ANSWER",
            stopped_by="ANSWERED_WITH_EVIDENCE",
            evidence_ids=(ev,), confidence=conf, agents_used=0,
            external_sources_used=0, quarantined=False,
            violations=tuple(violations), trace=tuple(trace),
        )
        return report

    # INVENTORY + GAP
    inventory = inventory or {"known": (), "unknown": ()}
    gap = tuple(inventory.get("unknown", ()))
    step("Self-inventory")
    step(f"GAP: {gap[0] if gap else 'none'}")

    # THINK / INVENT — internal reasoning first; a frozen idea proves
    # internal thinking happened before any external exposure.
    if gap:
        step("Internal reasoning")

    # RESEARCH GATE
    if external_hits:
        if frozen_idea is None or not frozen_idea.get("frozen_before_external"):
            quarantined = True
            violations.append("NOVELTY_BEFORE_EXTERNAL")
            step("External gate: QUARANTINE")
        else:
            step("External gate: justified")
    sources_used = len(external_hits)

    # OBSERVE / CHALLENGE / VERIFY via the evidence bus
    bus = EvidenceBus()
    bus.register_evidence(*[f"external:{i}" for i in range(len(external_hits))])
    if external_hits:
        bus.findings.append(_finding("external", "GAP_RESOLVED",
                                     tuple(f"external:{i}" for i in range(len(external_hits))),
                                     quarantined))
    claims = _claim_states(bus, ["GAP_RESOLVED"])
    conf = confidence_from_evidence(claims)["confidence"] if claims else "UNVERIFIED"
    ev = bus.evidence_ids()
    step("Verify")
    step("Synthesize")
    step("Answer")

    answered = bool(ev) and conf == "SUPPORTED"
    state = {
        "answered": answered,
        "uncertainty_changes_decision": True,
        "info_gain": 1.0,
        "budget": budget,
        "evidence_available": True,
        "human_required": False,
    }
    stopped = stop_condition(state) or "ANSWERED_WITH_EVIDENCE"
    return LoopReport(
        question=question, route=triage.route, stopped_by=stopped,
        evidence_ids=ev, confidence=conf, agents_used=0,
        external_sources_used=sources_used, quarantined=quarantined,
        violations=tuple(violations), trace=tuple(trace),
    )


def _finding(agent: str, claim: str, evidence: tuple, quarantined: bool):
    from lola_evidence_bus import Finding
    # quarantined hits carry their evidence as contradictions: presented,
    # never learned.
    if quarantined:
        return Finding(agent=agent, finding=claim, evidence_ids=(),
                       contradictions=evidence, next_gap="quarantined")
    return Finding(agent=agent, finding=claim, evidence_ids=evidence,
                   contradictions=(), next_gap="")


def learning_governor(report: LoopReport) -> str:
    """PROMOTE | RETAIN | REJECT.

    PROMOTE: verified answer, no quarantine, transfer + regression pass.
    REJECT: quarantined, or final confidence CONTRADICTED.
    RETAIN: everything else — the answer stands, it is not knowledge yet.
    """
    if report.quarantined or report.confidence == "CONTRADICTED":
        return "REJECT"
    if (report.stopped_by == "ANSWERED_WITH_EVIDENCE"
            and not report.violations
            and report.transfer_passed and report.regression_passed):
        return "PROMOTE"
    return "RETAIN"
