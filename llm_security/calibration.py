"""Versioned calibration corpus, measured baseline, and (unset) release thresholds.

Three deliberately separate concepts — never collapse them:

1. **Fixture corpus**  — labelled evidence (``fixtures/calibration_v1.jsonl``).
   Sanitised structural indicators + benign canaries. No live attack payloads.
2. **Measured baseline** — observed detector behaviour on that corpus
   (``baseline_v1.measured.json``). Written ONLY by executing the pipeline,
   never hand-entered.
3. **Release threshold** — policy (``thresholds_v1.json``). Explicitly
   UNSET in v1: thresholds are a separate reviewed change made AFTER the
   measured distribution exists, so the benchmark is never tuned to a
   desired result.

Fail-closed invariants:
- ``UNMEASURED`` / ``total == 0`` must never be treated as passing.
- A baseline can only be written from a corpus containing BOTH classes
  and at least one case.
- Reports carry case IDs and aggregates only — never raw corpus text.

Pure stdlib; deterministic.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .guardrail_analyzer import analyse
from .pipeline import GuardPipeline

FIXTURE_VERSION = "cal-v1"
MEASURED_SCHEMA = "lola.guardrail.measured-baseline/v2"
THRESHOLD_SCHEMA = "lola.guardrail.release-threshold/v1"

_LABELS = ("attack", "benign")
_CASE_ID_RE = re.compile(r"^cal-v1-(BEN|ATT)-\d{3}$")


class CalibrationError(ValueError):
    """Raised when corpus structure is invalid (fail closed)."""


@dataclass(frozen=True)
class CalibrationCase:
    case_id: str
    prompt: str
    expected_label: str  # "attack" | "benign"
    family: str
    source: str
    fixture_version: str


def load_calibration(path: str | Path) -> list[CalibrationCase]:
    """Load and strictly validate a calibration fixture (JSONL)."""
    cases: list[CalibrationCase] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        row = json.loads(raw)
        case = _validate_row(row, lineno)
        if case.case_id in seen:
            raise CalibrationError(f"duplicate case_id {case.case_id!r} at line {lineno}")
        seen.add(case.case_id)
        cases.append(case)
    if not cases:
        raise CalibrationError("corpus is empty — a zero-case baseline is forbidden")
    return cases


def _validate_row(row: Mapping[str, Any], lineno: int) -> CalibrationCase:
    required = ("case_id", "prompt", "expected_label", "family", "source", "fixture_version")
    for key in required:
        if not str(row.get(key, "")).strip():
            raise CalibrationError(f"line {lineno}: missing field {key!r}")
    case_id = str(row["case_id"]).strip()
    if not _CASE_ID_RE.match(case_id):
        raise CalibrationError(f"line {lineno}: case_id {case_id!r} violates stable scheme cal-v1-<BEN|ATT>-<nnn>")
    version = str(row["fixture_version"]).strip()
    if not case_id.startswith(f"{version}-"):
        raise CalibrationError(f"line {lineno}: case_id {case_id!r} is not consistent with fixture_version {version!r}")
    label = str(row["expected_label"]).strip().lower()
    if label not in _LABELS:
        raise CalibrationError(f"line {lineno}: expected_label must be one of {_LABELS}, got {label!r}")
    if not str(row["prompt"]).strip():
        raise CalibrationError(f"line {lineno}: prompt must be non-empty")
    return CalibrationCase(
        case_id=case_id,
        prompt=str(row["prompt"]),
        expected_label=label,
        family=str(row["family"]).strip(),
        source=str(row["source"]).strip(),
        fixture_version=str(row["fixture_version"]).strip(),
    )


def corpus_manifest(cases: Iterable[CalibrationCase]) -> dict[str, Any]:
    """Versioning evidence for the corpus: hash + structural counts (no prompt text)."""
    rows = list(cases)
    versions = {c.fixture_version for c in rows}
    if len(versions) != 1:
        raise CalibrationError(f"mixed fixture versions: {sorted(versions)}")
    by_label = {label: 0 for label in _LABELS}
    by_family: dict[str, int] = {}
    for c in rows:
        by_label[c.expected_label] += 1
        by_family[c.family] = by_family.get(c.family, 0) + 1
    digest = hashlib.sha256()
    for c in rows:
        digest.update(f"{c.case_id}\u0000{c.prompt}\u0000{c.expected_label}\n".encode("utf-8"))
    return {
        "fixture_version": versions.pop(),
        "sha256": digest.hexdigest(),
        "total": len(rows),
        "by_label": by_label,
        "by_family": by_family,
        "case_ids": sorted(c.case_id for c in rows),
    }


# ---------------------------------------------------------------------------
# Mutation layer — deterministic, derived from the same labelled fixture.
# Mutations are robustness probes on EXISTING evidence, not new cases:
# labels are inherited, so a flip measures detector instability.
# ---------------------------------------------------------------------------

def _mutate_whitespace(text: str) -> str:
    return "  ".join(text.split(" ")) + "\n"


def _mutate_punctuation(text: str) -> str:
    return re.sub(r"[.,!?;:]", "", text)


def _mutate_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


MUTATIONS: dict[str, Any] = {
    "whitespace": _mutate_whitespace,
    "punctuation": _mutate_punctuation,
    "unicode": _mutate_unicode,
}


def mutation_variants(case: CalibrationCase) -> dict[str, CalibrationCase]:
    """Derived variants: same label, case_id suffixed ``--<kind>`` (deterministic)."""
    out: dict[str, CalibrationCase] = {}
    for kind, fn in MUTATIONS.items():
        mutated = fn(case.prompt)
        if mutated != case.prompt:
            out[kind] = CalibrationCase(
                case_id=f"{case.case_id}--{kind}",
                prompt=mutated,
                expected_label=case.expected_label,
                family=f"{case.family}::{kind}",
                source=case.source,
                fixture_version=case.fixture_version,
            )
    return out


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def _ratio(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def _detector_fingerprint(module_path: str | Path) -> str:
    return hashlib.sha256(Path(module_path).read_bytes()).hexdigest()


def measure_calibration(
    cases: Iterable[CalibrationCase],
    *,
    include_mutations: bool = True,
    detector_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Execute the guardrail over the corpus and return an AGGREGATE-ONLY report.

    Convention (documented, stable): detection = REVIEW|BLOCK;
    benign over-refusal = BLOCK only (the regression-gate convention).
    """
    rows = list(cases)
    by_label = {label: 0 for label in _LABELS}
    for c in rows:
        by_label[c.expected_label] += 1
    if by_label["attack"] == 0 or by_label["benign"] == 0:
        raise CalibrationError("corpus must contain BOTH attack and benign classes (fail closed)")

    tp = tn = fp = fn = 0
    benign_block = 0
    per_family: dict[str, dict[str, Any]] = {}
    flips: dict[str, list[dict[str, Any]]] = {kind: [] for kind in MUTATIONS}
    variant_counts = {kind: 0 for kind in MUTATIONS}

    def _score(case: CalibrationCase) -> None:
        nonlocal tp, tn, fp, fn, benign_block
        decision = analyse(case.prompt).decision
        predicted = decision in {"REVIEW", "BLOCK"}
        actual = case.expected_label == "attack"
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1
        if case.expected_label == "benign" and decision == "BLOCK":
            benign_block += 1
        fam = per_family.setdefault(case.family, {"total": 0, "detected": 0, "blocked_benign": 0})
        fam["total"] += 1
        if case.expected_label == "attack":
            fam["detected"] += 1 if predicted else 0
        elif decision == "BLOCK":
            fam["blocked_benign"] += 1

    base_decisions: dict[str, str] = {}
    for c in rows:
        base_decisions[c.case_id] = analyse(c.prompt).decision
    for c in rows:
        _score(c)

    if include_mutations:
        for c in rows:
            for kind, variant in mutation_variants(c).items():
                variant_counts[kind] += 1
                decision = analyse(variant.prompt).decision
                predicted = decision in {"REVIEW", "BLOCK"}
                fam = per_family.setdefault(variant.family, {"total": 0, "detected": 0, "blocked_benign": 0})
                fam["total"] += 1
                if variant.expected_label == "attack":
                    fam["detected"] += 1 if predicted else 0
                elif decision == "BLOCK":
                    fam["blocked_benign"] += 1
                if decision != base_decisions[c.case_id]:
                    flips[kind].append(
                        {"case_id": variant.case_id, "from": base_decisions[c.case_id], "to": decision}
                    )

    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = round((2 * precision * recall / (precision + recall)), 4) if precision + recall else 0.0
    benign_total = by_label["benign"]
    attack_total = by_label["attack"]

    return {
        "schema": MEASURED_SCHEMA,
        "status": "MEASURED",
        "conventions": {"detection": "REVIEW|BLOCK", "benign_over_refusal": "BLOCK only"},
        "detector": {"module": "llm_security.guardrail_analyzer", "fingerprint": detector_fingerprint},
        "metrics": {
            "total": tp + tn + fp + fn,
            "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall, "f1": f1,
            "false_positive_rate": _ratio(fp, fp + tn),
            "false_negative_rate": _ratio(fn, fn + tp),
            "benign_over_refusal": _ratio(benign_block, benign_total),
            "attack_total": attack_total,
            "benign_total": benign_total,
        },
        "per_family": per_family,
        "mutation_sensitivity": {
            kind: {"variants": variant_counts[kind], "flips": len(items)}
            for kind, items in flips.items()
        },
        "mutation_flips": {kind: items for kind, items in flips.items()},
        "artifact_policy": "aggregates and case_ids only; no raw corpus text",
    }


def write_measured_baseline(report: Mapping[str, Any], path: str | Path) -> None:
    """Persist a measured baseline. Refuses unless the report is MEASURED and non-zero."""
    if report.get("status") != "MEASURED":
        raise CalibrationError(f"refusing to write baseline: status={report.get('status')!r} (fail closed)")
    m = report["metrics"]
    if m["total"] == 0 or m["attack_total"] == 0 or m["benign_total"] == 0:
        raise CalibrationError("refusing to write baseline: zero-case or single-class corpus (fail closed)")
    Path(path).write_text(json.dumps(dict(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_measured_baseline(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def baseline_drift(committed: Mapping[str, Any], fresh: Mapping[str, Any]) -> list[str]:
    """Diff committed measured baseline against a fresh measurement.

    Covers every section that can silently change: metrics, per-family,
    mutation sensitivity, the detector fingerprint (a changed detector must
    invalidate the baseline even if metrics coincidentally match), and the
    corpus manifest (fixture version / sha256).
    """
    drift: list[str] = []
    for section in ("metrics", "per_family", "mutation_sensitivity", "detector", "corpus"):
        a, b = committed.get(section), fresh.get(section)
        if a != b:
            if isinstance(a, Mapping) and isinstance(b, Mapping):
                for key in sorted(set(a) | set(b)):
                    if a.get(key) != b.get(key):
                        drift.append(f"{section}.{key}")
            else:
                drift.append(section)
    return drift


# ---------------------------------------------------------------------------
# Release thresholds — policy, separate schema, UNSET in v1.
# ---------------------------------------------------------------------------

def load_release_thresholds(path: str | Path) -> dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema") != THRESHOLD_SCHEMA:
        raise CalibrationError(f"threshold doc schema mismatch: {doc.get('schema')!r}")
    if doc.get("status") == "UNSET":
        if doc.get("policy") is not None:
            raise CalibrationError("thresholds are UNSET but carry a policy — inconsistent (fail closed)")
    return doc
