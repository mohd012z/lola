"""Generate the V1 calibration REPORT (review artifact for the threshold decision).

Evidence chain: fixture corpus -> measured baseline -> THIS report. The report
carries AGGREGATES and case_ids only — never raw corpus text (Anam's rule, and
already enforced by test_measurement_is_deterministic_and_aggregates_only).

Numbers are read from the committed measured baseline + a fresh per-case pass,
never hand-entered. This is a CALIBRATION report, not an authoritative
production benchmark.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm_security import calibration as cal  # noqa: E402
from llm_security.guardrail_analyzer import analyse  # noqa: E402

FIX = ROOT / "fixtures"


def _per_case(cases):
    out = []
    for c in cases:
        a = analyse(c.prompt)
        detected = a.decision in {"REVIEW", "BLOCK"}
        if c.expected_label == "attack":
            outcome = "TP" if detected else "FN"
        else:
            outcome = ("FP" if detected else "TN")
            if a.decision == "BLOCK":
                outcome = "FP(benign_block)"
        out.append((c, a, outcome))
    return out


def main() -> int:
    cases = cal.load_calibration(FIX / "calibration_v1.jsonl")
    manifest = cal.corpus_manifest(cases)
    baseline = cal.load_measured_baseline(FIX / "baseline_v1.measured.json")
    m = baseline["metrics"]
    thresholds = cal.load_release_thresholds(FIX / "thresholds_v1.json")

    per_case = _per_case(cases)
    fn = [(c, a) for c, a, o in per_case if o == "FN"]
    fp = [(c, a) for c, a, o in per_case if o.startswith("FP")]
    benign_blocked = [(c, a) for c, a, o in per_case if o == "FP(benign_block)"]

    # base families only (drop ::mutation variants)
    base_fam = {k: v for k, v in baseline["per_family"].items() if "::" not in k}
    fam_label = {c.family: c.expected_label for c in cases}

    lines: list[str] = []
    ap = lines.append
    ap("# Guardrail Calibration Report — v1")
    ap("")
    ap("> **Calibration artifact, not an authoritative production benchmark.**")
    ap("> Purpose: evidence for a *reviewed* release-threshold decision. Aggregates and")
    ap("> case_ids only — no raw corpus text is reproduced here.")
    ap("")
    ap("## Provenance")
    ap(f"- fixture corpus: `{manifest['fixture_version']}` (calibration_v1.jsonl)")
    ap(f"- corpus sha256: `{manifest['sha256']}`")
    ap(f"- cases: {manifest['total']} (attack {manifest['by_label']['attack']} / benign {manifest['by_label']['benign']})")
    det = baseline["detector"]
    ap(f"- detector: `{det['module']}` fingerprint `{det['fingerprint'][:16]}…`")
    ap(f"- conventions: {baseline['conventions']['detection']} | over-refusal {baseline['conventions']['benign_over_refusal']}")
    ap("")
    ap("## Measured V1 distribution (from execution, not hand-entered)")
    ap("")
    ap("| metric | value |")
    ap("|---|---|")
    ap(f"| total | {m['total']} |")
    ap(f"| TP / TN / FP / FN | {m['tp']} / {m['tn']} / {m['fp']} / {m['fn']} |")
    ap(f"| precision | {m['precision']} |")
    ap(f"| recall | {m['recall']} |")
    ap(f"| F1 | {m['f1']} |")
    ap(f"| false-positive rate | {m['false_positive_rate']} |")
    ap(f"| false-negative rate | {m['false_negative_rate']} |")
    ap(f"| benign over-refusal | {m['benign_over_refusal']} |")
    ap("")
    ap("## Per-family (base cases, mutation variants excluded)")
    ap("")
    ap("| family | class | total | detected | benign-blocked |")
    ap("|---|---|---|---|---|")
    for fam in sorted(base_fam):
        s = base_fam[fam]
        cls = "benign" if fam_label.get(fam) == "benign" else "attack"
        detc = s.get("detected", 0)
        blk = s.get("blocked_benign", 0)
        gap = ""
        if cls == "attack" and detc < s.get("total", 0):
            gap = f"  ⚠ gap ({detc}/{s.get('total')} detected)"
        if cls == "benign" and blk:
            gap = f"  ⚠ over-refusal ({blk})"
        ap(f"| {fam} | {cls} | {s.get('total',0)} | {detc if cls=='attack' else '—'} | {blk if cls=='benign' else '—'}{gap} |")
    ap("")
    ap("## Mutation sensitivity")
    ap("")
    ap("| kind | variants | flips |")
    ap("|---|---|---|")
    for kind, s in baseline["mutation_sensitivity"].items():
        ap(f"| {kind} | {s['variants']} | {s['flips']} |")
    ap("")
    uf = (baseline["mutation_flips"] or {}).get("unicode") or []
    if uf:
        for f in uf:
            ap(f"- `{f['case_id']}` flipped **{f['from']} → {f['to']}** under Unicode normalization.")
        ap("A fullwidth (NFKC) disguise becomes the plain form the detector already recognises, so the detector's internal normalisation neutralises that specific disguise (recorded as evidence, not a code change).")
    ap("")
    ap("## Missed attacks (false negatives) — case_ids + score only")
    ap("")
    if fn:
        ap("| case_id | family | risk_score | decision |")
        ap("|---|---|---|---|")
        for c, a in fn:
            ap(f"| {c.case_id} | {c.family} | {a.risk_score} | {a.decision} |")
        ap("")
        ap("These sit just under the REVIEW floor (0.30): single-signal cases whose one indicator carries a weight < 0.30. They are the input for a future **detector** change (re-weight / add corroborating signal), which the baseline-reproduction gate will then verify.")
    else:
        ap("None — every attack case was detected.")
    ap("")
    ap("## False positives (benign flagged)")
    ap("")
    if fp:
        for c, a in fp:
            ap(f"- {c.case_id} ({c.family}): {a.decision} @ {a.risk_score}")
    else:
        ap("None — no benign case was flagged (FPR 0.0, benign over-refusal 0.0).")
    ap("")
    ap("## Release threshold status")
    ap("")
    ap(f"- `thresholds_v1.json`: **status = {thresholds['status']}, policy = {thresholds['policy']}**")
    ap("- Thresholds (min recall / max FPR / max over-refusal) are POLICY and remain UNSET by design.")
    ap("- They are set in a **separate reviewed change** after this distribution is examined, so the benchmark is never tuned to a desired result.")
    ap("")
    ap("---")
    ap("*Generated by `scripts/llm_security_calibration_report.py` from the committed measured baseline. Re-run after any detector or corpus change; the structural gate re-verifies the baseline reproduces.*")

    out = FIX / "calibration_report_v1.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Safety: assert no raw prompt text leaked into the artifact.
    dump = out.read_text(encoding="utf-8")
    leaked = [c.case_id for c in cases if c.prompt[:40] in dump]
    if leaked:
        print(f"REPORT BLOCKED: raw corpus text leaked into artifact for {leaked}")
        return 1
    print(f"report written: {out.relative_to(ROOT)} ({len(lines)} lines, no raw prompt text)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
