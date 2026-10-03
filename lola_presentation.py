"""Presentation — /style, evidence-based confidence, safe /flow trace.

docs/superpowers/specs/new-lola-cognitive-mesh-controls.md, Module G.

Two hard rules this module enforces:

1. STYLE NEVER CHANGES INVESTIGATION. A style transform acts on an
   already-verified answer structure. Required sections survive every
   style in the same order — presentation can compress or rephrase
   optionals, never drop the truth.

2. CONFIDENCE COMES FROM EVIDENCE, NOT FEELING. We never emit a
   fabricated percentage ("94%"). We emit the evidence-state string
   (SUPPORTED / PARTIALLY_SUPPORTED / CONTRADICTED / UNVERIFIED) plus
   the evidence ids that justify it. Agent count is not evidence:
   four models agreeing is not four independent observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

STYLES = ("AUTO", "COMPACT", "BEGINNER", "TECHNICAL", "ENGINEER",
          "MANAGER", "RESEARCH", "AUDIT", "TUTORIAL", "TABLE", "DIAGRAM")


@dataclass(frozen=True)
class Section:
    title: str
    text: str
    required: bool = True


@dataclass(frozen=True)
class Answer:
    sections: tuple  # tuple[Section, ...]
    lead: str = ""


def apply_style(answer: Answer, style: str) -> Answer:
    """Transform presentation only. Required sections always survive."""
    if style not in STYLES:
        raise ValueError(f"unknown style: {style}")
    sections = list(answer.sections)

    if style == "COMPACT":
        # drop optional sections; truncate verbose required text (marked)
        out = []
        for s in sections:
            if not s.required:
                continue
            text = s.text
            if len(text) > 160:
                text = text[:157] + " [...]"
            out.append(Section(s.title, text, required=True))
        return Answer(sections=tuple(out), lead="")

    if style == "BEGINNER":
        # plain-language lead from the first required section
        first_req = next((s for s in sections if s.required), None)
        lead = ""
        if first_req is not None:
            sentence = first_req.text.strip().split(". ")[0]
            lead = "In short: " + sentence
        return Answer(sections=tuple(sections), lead=lead)

    # AUTO / TECHNICAL / ENGINEER / MANAGER / RESEARCH / AUDIT /
    # TUTORIAL / TABLE / DIAGRAM are identity transforms in v1: the
    # contract (required sections preserved, order stable) is in place;
    # richer transforms are added later without changing it.
    return Answer(sections=tuple(sections), lead=answer.lead)


def confidence_from_evidence(claims: Sequence[Mapping[str, Any]]) -> dict:
    """Evidence-state string + provenance. Never a percentage.

    CONTRADICTED wins (any contradicted claim poisons the answer);
    else SUPPORTED (every claim has evidence); else PARTIALLY_SUPPORTED
    (some claims have evidence, some don't); else UNVERIFIED.
    """
    states = [str(c.get("state", "UNVERIFIED")).upper() for c in claims]
    if not claims:
        return {"confidence": "UNVERIFIED", "evidence_ids": [], "provenance": []}
    if "CONTRADICTED" in states:
        conf = "CONTRADICTED"
    elif all(c.get("evidence_ids") for c in claims):
        conf = "SUPPORTED"
    elif any(c.get("evidence_ids") for c in claims):
        conf = "PARTIALLY_SUPPORTED"
    else:
        conf = "UNVERIFIED"
    evidence_ids = sorted({str(e) for c in claims for e in (c.get("evidence_ids") or [])})
    provenance = [
        {"claim": c.get("id"), "state": str(c.get("state", "UNVERIFIED")).upper(),
         "evidence_ids": sorted(str(e) for e in (c.get("evidence_ids") or []))}
        for c in claims
    ]
    return {"confidence": conf, "evidence_ids": evidence_ids,
            "provenance": provenance}


_MARK = {"done": "✓", "in-progress": "●", "pending": "○"}


def render_flow(
    trace: Sequence[Mapping[str, Any]],
    *,
    task_id: str,
    external_ai_used: bool,
    evidence_count: int,
    current_uncertainty: str,
) -> str:
    """Safe operational trace: actions, sources, states, decisions.

    Never raw chain-of-thought — only the steps and their status,
    whether external AI has been used, how much evidence there is, and
    the current uncertainty.
    """
    lines = [f"TASK #{task_id}", ""]
    for step in trace:
        status = str(step.get("status", "pending"))
        mark = _MARK.get(status, "○")
        lines.append(f"{mark} {step.get('step')}")
    lines.append("")
    lines.append("External AI:")
    lines.append("used" if external_ai_used else "not used yet")
    lines.append("")
    lines.append(f"Evidence:")
    lines.append(f"{evidence_count} observations")
    lines.append("")
    lines.append("Current uncertainty:")
    lines.append(current_uncertainty)
    return "\n".join(lines)
