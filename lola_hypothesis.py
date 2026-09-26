#!/usr/bin/env python3
"""Small hypothesis engine for evidence-driven Lola analysis."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable
from lola_evidence import Evidence, EvidenceLedger, Finding


@dataclass
class Hypothesis:
    statement: str
    expected_kinds: set[str] = field(default_factory=set)
    finding: Finding | None = None

    def evaluate(self, ledger: EvidenceLedger, observations: Iterable[Evidence]) -> Finding:
        observations = list(observations)
        item = ledger.finding(self.statement)
        for observation in observations:
            if not self.expected_kinds or observation.kind in self.expected_kinds:
                ledger.add(self.statement, observation)
        self.finding = item
        return item

    def missing_evidence(self) -> list[str]:
        if self.finding is None:
            return sorted(self.expected_kinds)
        present = {x.kind for x in self.finding.evidence}
        return sorted(self.expected_kinds - present)


def cross_check(statement: str, ledger: EvidenceLedger, observations: Iterable[Evidence], expected: set[str]) -> dict:
    hypothesis = Hypothesis(statement=statement, expected_kinds=expected)
    finding = hypothesis.evaluate(ledger, observations)
    return {
        "finding": finding.to_dict(),
        "missingEvidence": hypothesis.missing_evidence(),
    }
