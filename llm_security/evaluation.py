"""Deterministic aggregate evaluation for Lola's defensive guardrail.

Evaluation consumes labelled fixtures but reports aggregate metrics only. It has
no ALLOW/REVIEW/BLOCK authority and does not persist raw fixture text.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .pipeline import GuardPipeline


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    label: str
    text: str

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id is required")
        if self.label not in {"attack", "benign"}:
            raise ValueError("label must be attack or benign")


@dataclass(frozen=True)
class EvaluationReport:
    valid: bool
    total: int
    attack_total: int
    benign_total: int
    tp: int
    tn: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    fpr: float
    fnr: float
    benign_over_refusal: float
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def evaluate_cases(
    cases: Iterable[EvaluationCase], *, pipeline: GuardPipeline | None = None
) -> EvaluationReport:
    """Evaluate labelled fixtures; REVIEW/BLOCK count as defensive detection."""
    pipeline = pipeline or GuardPipeline()
    tp = tn = fp = fn = 0

    for case in cases:
        detected = pipeline.evaluate(case.text).action in {"REVIEW", "BLOCK"}
        if case.label == "attack":
            if detected:
                tp += 1
            else:
                fn += 1
        else:
            if detected:
                fp += 1
            else:
                tn += 1

    attack_total = tp + fn
    benign_total = tn + fp
    failures: list[str] = []
    if not attack_total:
        failures.append("missing_attack_controls")
    if not benign_total:
        failures.append("missing_benign_controls")

    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, attack_total)
    f1 = _ratio(2 * precision * recall, precision + recall)
    fpr = _ratio(fp, benign_total)
    fnr = _ratio(fn, attack_total)

    return EvaluationReport(
        valid=not failures,
        total=attack_total + benign_total,
        attack_total=attack_total,
        benign_total=benign_total,
        tp=tp,
        tn=tn,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        fpr=fpr,
        fnr=fnr,
        benign_over_refusal=fpr,
        failures=tuple(failures),
    )
