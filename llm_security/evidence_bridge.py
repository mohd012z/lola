"""Bridge defensive prompt analysis into Lola's evidence ledger."""
from __future__ import annotations

from lola_evidence import Evidence, EvidenceLedger
from .guardrail_analyzer import Analysis, analyse


def analyse_with_evidence(text: str) -> tuple[Analysis, EvidenceLedger]:
    result = analyse(text)
    ledger = EvidenceLedger(f"prompt:{result.fingerprint[:16]}")
    statement = "input contains structural indicators associated with prompt injection or jailbreak behavior"

    for signal in result.signals:
        ledger.add(
            statement,
            Evidence(
                kind="llm_guardrail_signal",
                source=result.fingerprint,
                observation=signal.name,
                locator=signal.evidence,
                tool="guardrail-analyzer",
                weight=signal.score,
                metadata={"decision": result.decision},
            ),
        )

    return result, ledger
