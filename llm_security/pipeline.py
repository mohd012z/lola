"""Primary/secondary defensive decision pipeline for Lola LLM security."""
from __future__ import annotations

from dataclasses import dataclass

from .guardrail_analyzer import Analysis, analyse
from .protocol import WorkerResult


@dataclass(frozen=True)
class PipelineDecision:
    action: str
    risk_score: float
    primary: Analysis
    secondary_score: float
    reasons: tuple[str, ...]


class SecondaryVerifier:
    """Independent evidence aggregation; it does not authorize execution."""

    def verify(self, results: list[WorkerResult]) -> tuple[float, tuple[str, ...]]:
        if not results:
            return 0.0, ()
        score = max(r.max_score for r in results)
        reasons = tuple(
            f"{finding.worker}:{finding.kind}@{finding.locator}"
            for result in results
            for finding in result.findings
        )
        return min(score, 1.0), reasons


class PrimaryPolicy:
    """Single authority that converts observations into a defensive decision."""

    def resolve(self, primary: Analysis, secondary_score: float, reasons: tuple[str, ...]) -> PipelineDecision:
        risk = max(primary.risk_score, secondary_score)
        # Preserve existing Lola thresholds until benchmark calibration provides
        # evidence for changing them.
        if risk >= 0.65:
            action = "BLOCK"
        elif risk >= 0.30:
            action = "REVIEW"
        else:
            action = "ALLOW"
        return PipelineDecision(action, round(risk, 3), primary, secondary_score, reasons)


class GuardPipeline:
    def __init__(self, verifier: SecondaryVerifier | None = None, policy: PrimaryPolicy | None = None):
        self.verifier = verifier or SecondaryVerifier()
        self.policy = policy or PrimaryPolicy()

    def evaluate(self, text: str, worker_results: list[WorkerResult] | None = None) -> PipelineDecision:
        primary = analyse(text)
        secondary_score, reasons = self.verifier.verify(worker_results or [])
        return self.policy.resolve(primary, secondary_score, reasons)
