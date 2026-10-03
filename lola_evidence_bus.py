"""Evidence bus — shared state, isolated working context.

docs/superpowers/specs/new-lola-runtime-loop-v1.md, Module J.

Agents (or any worker) submit compressed FINDINGS, not essays:
finding + evidence ids + unknowns + contradictions + next gap. The
bus holds the shared state; each worker keeps its own scratch.

The decisive rule: **evidence wins, not agent count.** A claim wins
only if bus evidence discriminates between the claims AND one claim is
contradicted (or the winner is supported while the loser is not).
Two claims backed by the same evidence are both unverified — nobody
wins by headcount.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class Finding:
    agent: str
    finding: str
    evidence_ids: Sequence[str] = ()
    unknowns: Sequence[str] = ()
    contradictions: Sequence[str] = ()
    next_gap: str = ""


class EvidenceBus:
    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self._evidence: set[str] = set()

    def register_evidence(self, *ids: str) -> None:
        self._evidence.update(ids)

    def evidence_ids(self) -> tuple:
        return tuple(sorted(self._evidence))

    def submit(self, finding: Finding) -> None:
        # pollution guard: only evidence that exists on the bus may be
        # cited; unknown ids are a hard error, not a warning.
        unknown = [e for e in finding.evidence_ids if e not in self._evidence]
        if unknown:
            raise ValueError(f"unknown evidence ids: {unknown}")
        unknown_c = [e for e in finding.contradictions if e not in self._evidence]
        if unknown_c:
            raise ValueError(f"unknown contradiction evidence ids: {unknown_c}")
        self.findings.append(finding)

    def _for(self, claim: str) -> list[Finding]:
        return [f for f in self.findings if f.finding == claim]

    def _supports(self, claim: str) -> set:
        return {e for f in self._for(claim) for e in f.evidence_ids}

    def _contradicts(self, claim: str) -> set:
        """Evidence self-reported as undermining `claim`.

        A finding lists, in its own contradictions field, the evidence
        that contradicts ITS OWN claim. Cross-claim attacks are not
        counted: only the worker that produced a claim is in a position
        to report what refutes it.
        """
        return {e for f in self.findings if f.finding == claim
                for e in f.contradictions}

    def discriminating_evidence(self, claim_a: str, claim_b: str) -> tuple:
        """Evidence that discriminates A from B.

        Requires evidence on BOTH sides that differs: one side citing
        evidence the other does not. A single side's evidence alone is
        not a discrimination (absence of evidence for the other claim
        is not evidence against it), and identical citations from both
        sides discriminate nothing.
        """
        sa, sb = self._supports(claim_a), self._supports(claim_b)
        if not sa or not sb:
            return ()
        return tuple(sorted((sa - sb) | (sb - sa)))

    def verdict(self, claim_a: str, claim_b: str):
        """-> (winner | None, discriminating: bool, note: str)

        A winner requires discriminating evidence AND exactly one claim
        self-reported as contradicted. Support without contradiction
        keeps both claims open; agent count never decides.
        """
        disc = self.discriminating_evidence(claim_a, claim_b)
        if not disc:
            return None, False, (
                "evidence does not discriminate; claims stand unverified "
                "— no winner by agent count"
            )
        contra_a = self._contradicts(claim_a)
        contra_b = self._contradicts(claim_b)
        if contra_a and contra_b:
            return None, True, "both claims contradicted; keep both open"
        if contra_a and not contra_b:
            return claim_b, True, f"{claim_a} contradicted by {sorted(contra_a)}"
        if contra_b and not contra_a:
            return claim_a, True, f"{claim_b} contradicted by {sorted(contra_b)}"
        return None, True, (
            "discriminating evidence exists but contradicts neither "
            "claim decisively; keep both open"
        )
