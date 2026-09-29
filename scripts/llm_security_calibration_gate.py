"""CI quality gate for the calibration corpus — STRUCTURAL, not numeric.

Anam's rule (P5, first half only): do NOT enforce min-recall / max-FPR yet —
those thresholds are a separate reviewed change made after the measured
distribution exists. This gate enforces only that the EVIDENCE chain is intact:

  1. corpus loads and is structurally valid (both classes, >=1 case, stable IDs)
  2. the committed measured baseline reproduces from a FRESH execution
     (no hand-entered numbers: if the code or corpus changed, CI fails)
  3. the release-threshold file is status=UNSET with policy=null while we
     have not yet reviewed the measured distribution
  4. the legacy baseline.json is still UNMEASURED (fail-closed sentinel;
     it is never converted to GREEN by this gate or by any numeric change)

Exit 0 = chain intact. Exit 1 = fail closed. Prints a short evidence summary.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm_security import calibration as cal  # noqa: E402

FIX = ROOT / "fixtures"


def main() -> int:
    corpus = cal.load_calibration(FIX / "calibration_v1.jsonl")
    manifest = cal.corpus_manifest(corpus)
    if manifest["by_label"]["attack"] == 0 or manifest["by_label"]["benign"] == 0:
        print("GATE FAIL: corpus must contain both attack and benign classes")
        return 1

    committed = cal.load_measured_baseline(FIX / "baseline_v1.measured.json")
    fresh = cal.measure_calibration(
        corpus,
        include_mutations=True,
        detector_fingerprint=cal._detector_fingerprint(ROOT / "llm_security" / "guardrail_analyzer.py"),
    )
    fresh["corpus"] = manifest
    drift = cal.baseline_drift(committed, fresh)
    if drift:
        print("GATE FAIL: committed measured baseline drifted from fresh execution:")
        for d in drift:
            print(f"  - {d}")
        return 1

    thresholds = cal.load_release_thresholds(FIX / "thresholds_v1.json")
    if thresholds.get("status") != "UNSET" or thresholds.get("policy") is not None:
        print("GATE FAIL: release thresholds must stay UNSET/policy=null until a reviewed threshold change")
        return 1

    legacy = (ROOT / "llm_security" / "baseline.json").read_text(encoding="utf-8")
    if '"status": "UNMEASURED"' not in legacy or '"total": 0' not in legacy:
        print("GATE FAIL: legacy baseline.json must remain UNMEASURED + total: 0 (fail-closed sentinel)")
        return 1

    m = committed["metrics"]
    print(
        "GATE PASS: corpus "
        f"v{manifest['fixture_version']} sha256={manifest['sha256'][:12]} total={m['total']} "
        f"(attack={m['attack_total']}, benign={m['benign_total']}); "
        f"measured recall={m['recall']} fpr={m['false_positive_rate']} "
        f"benign_over_refusal={m['benign_over_refusal']}; "
        "thresholds=UNSET; legacy baseline=UNMEASURED."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
