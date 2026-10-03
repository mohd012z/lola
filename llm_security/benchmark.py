"""Small, deterministic regression harness for Lola guardrail evaluation."""
from __future__ import annotations

from typing import Iterable, Mapping, Any
from .guardrail_analyzer import analyse


def _ratio(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def benchmark(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    tp = tn = fp = fn = 0
    total = 0
    for row in rows:
        text = str(row.get("prompt", ""))
        label = str(row.get("label", "unknown")).lower()
        if label not in {"attack", "benign"}:
            continue
        total += 1
        predicted_attack = analyse(text).decision in {"REVIEW", "BLOCK"}
        actual_attack = label == "attack"
        if predicted_attack and actual_attack:
            tp += 1
        elif predicted_attack and not actual_attack:
            fp += 1
        elif not predicted_attack and actual_attack:
            fn += 1
        else:
            tn += 1

    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = round((2 * precision * recall / (precision + recall)), 4) if precision + recall else 0.0
    return {
        "total": total,
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": _ratio(fp, fp + tn),
    }
