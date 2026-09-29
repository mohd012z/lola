"""TASK 1C — calibration corpus, mutation layer, measured baseline, structural gate.

Three-layer contract (Anam, 2026-09-29):
  fixture corpus (evidence) / measured baseline (observed) / release threshold (policy)
— separate schemas and version histories. Thresholds stay UNSET; the legacy
UNMEASURED baseline.json stays a fail-closed sentinel; numbers below are
ASSERTED FROM THE MEASUREMENT, never hand-entered.
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm_security import calibration as cal  # noqa: E402
from llm_security.calibration import (  # noqa: E402
    CalibrationCase,
    CalibrationError,
    baseline_drift,
    corpus_manifest,
    load_calibration,
    load_measured_baseline,
    load_release_thresholds,
    measure_calibration,
    mutation_variants,
    write_measured_baseline,
)

FIX = ROOT / "fixtures"
CORPUS = FIX / "calibration_v1.jsonl"
BASELINE = FIX / "baseline_v1.measured.json"
THRESHOLDS = FIX / "thresholds_v1.json"
LEGACY = ROOT / "llm_security" / "baseline.json"


def _cases() -> list[CalibrationCase]:
    return load_calibration(CORPUS)


def _measure(cases, *, include_mutations=True):
    report = cal.measure_calibration(
        cases,
        include_mutations=include_mutations,
        detector_fingerprint=cal._detector_fingerprint(ROOT / "llm_security" / "guardrail_analyzer.py"),
    )
    report["corpus"] = corpus_manifest(cases)
    return report


# --------------------------------------------------------------------------
# 1. Corpus schema
# --------------------------------------------------------------------------

def test_corpus_loads_with_valid_schema():
    cases = _cases()
    assert len(cases) >= 10
    for c in cases:
        assert c.case_id.startswith("cal-v1-")
        assert c.expected_label in {"attack", "benign"}
        assert c.fixture_version == "cal-v1"
        assert c.family and c.source
        assert c.prompt.strip()


def test_corpus_has_both_classes_and_family_coverage():
    cases = _cases()
    manifest = corpus_manifest(cases)
    assert manifest["by_label"]["attack"] > 0
    assert manifest["by_label"]["benign"] > 0
    # every required family is represented (Fatah's spec)
    families = set(manifest["by_family"])
    for required in ("ordinary_coding", "defensive_security_discussion",
                     "academic_educational", "quotation_reference",
                     "policy_discussion", "ambiguous_benign",
                     "hierarchy_conflict", "role_manipulation",
                     "hidden_instruction_request", "safety_evasion"):
        assert required in families, f"missing family {required}"


def test_corpus_manifest_stable_and_fingerprinted():
    m1 = corpus_manifest(_cases())
    m2 = corpus_manifest(_cases())
    assert m1 == m2
    assert len(m1["sha256"]) == 64
    assert m1["case_ids"] == sorted(m1["case_ids"])


def test_corpus_validation_rejects_bad_rows(tmp_path):
    def _write(rows: str) -> Path:
        p = tmp_path / "bad.jsonl"
        p.write_text(rows, encoding="utf-8")
        return p

    good = ("{\"case_id\": \"cal-v1-ATT-001\", \"prompt\": \"x\", \"expected_label\": \"attack\", "
            "\"family\": \"f\", \"source\": \"s\", \"fixture_version\": \"cal-v1\"}\n")
    with pytest.raises(CalibrationError):
        cal.load_calibration(_write(""))                       # empty corpus
    with pytest.raises(CalibrationError):
        cal.load_calibration(_write(good + good))               # duplicate id
    with pytest.raises(CalibrationError):
        cal.load_calibration(_write(good.replace("ATT-001", "ATT-1")))  # unstable id
    with pytest.raises(CalibrationError):
        cal.load_calibration(_write(good.replace('"attack"', '"suspicious"')))  # bad label
    with pytest.raises(CalibrationError):
        cal.load_calibration(_write(good.replace('"cal-v1"', '"cal-v9"')))  # mixed versions


# --------------------------------------------------------------------------
# 2/3. Benign canaries + sanitised families (labelled, in-repo)
# --------------------------------------------------------------------------

def test_benign_canaries_present():
    cases = _cases()
    benign = [c for c in cases if c.expected_label == "benign"]
    assert len(benign) >= 5
    assert any(c.family == "ordinary_coding" for c in benign)
    assert any(c.family == "ambiguous_benign" for c in benign)


def test_adversarial_cases_are_structural_indicators_not_payloads():
    # Sanitised indicators only: short structural sentences, no weaponised content.
    cases = [c for c in _cases() if c.expected_label == "attack"]
    assert len(cases) >= 5
    assert all(len(c.prompt) < 200 for c in cases)
    assert all(c.source in {"indicator", "composite", "disguise"} for c in cases)


# --------------------------------------------------------------------------
# 4. Mutation layer
# --------------------------------------------------------------------------

def test_mutation_variants_inherit_label_and_are_stable():
    cases = _cases()
    for c in cases:
        for kind, v in mutation_variants(c).items():
            assert v.case_id == f"{c.case_id}--{kind}"
            assert v.expected_label == c.expected_label
            assert v.prompt != c.prompt
    assert mutation_variants(cases[0]) == mutation_variants(cases[0])


def test_fullwidth_disguise_flips_under_unicode_normalisation():
    cases = {c.case_id: c for c in _cases()}
    c = cases["cal-v1-ATT-010"]
    assert c.family == "obfuscation_indicator"
    variants = mutation_variants(c)
    assert "unicode" in variants
    # NFKC turns the fullwidth disguise into the plain indicator form, which
    # the detector then recognises — the mutation layer records that flip.
    full = _measure(_cases())
    assert full["mutation_sensitivity"]["unicode"]["flips"] >= 1
    flip = next(f for f in full["mutation_flips"]["unicode"] if f["case_id"] == c.case_id + "--unicode")
    assert flip["from"] != flip["to"]


# --------------------------------------------------------------------------
# 5. Measurement (numbers asserted FROM execution, not hand-entered)
# --------------------------------------------------------------------------

def test_measurement_reproduces_committed_baseline_exactly():
    committed = load_measured_baseline(BASELINE)
    fresh = _measure(_cases())
    assert fresh["metrics"] == committed["metrics"]
    assert fresh["per_family"] == committed["per_family"]
    assert fresh["mutation_sensitivity"] == committed["mutation_sensitivity"]
    assert baseline_drift(committed, fresh) == []


def test_measurement_is_deterministic_and_aggregates_only():
    r1 = _measure(_cases())
    r2 = _measure(_cases())
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
    dump = json.dumps(r1, sort_keys=True)
    # no raw corpus text in the report
    for c in _cases():
        assert c.prompt not in dump
        assert c.prompt[:40] not in dump


def test_measurement_math_is_exact_on_stubbed_detector(monkeypatch):
    # Independent of the real detector: a stub that detects iff 'zzz' is present.
    from llm_security import guardrail_analyzer as ga

    class _A:
        def __init__(self, d):
            self.decision = d

    def fake_analyse(text: str):
        return _A("BLOCK" if "zzz" in text else "ALLOW")

    monkeypatch.setattr(cal, "analyse", fake_analyse)
    cases = [
        CalibrationCase("cal-v1-ATT-001", "go zzz", "attack", "hierarchy_conflict", "s", "cal-v1"),
        CalibrationCase("cal-v1-ATT-002", "zzz again", "attack", "hierarchy_conflict", "s", "cal-v1"),
        CalibrationCase("cal-v1-ATT-003", "invisible", "attack", "hierarchy_conflict", "s", "cal-v1"),
        CalibrationCase("cal-v1-BEN-001", "hello", "benign", "ordinary_coding", "s", "cal-v1"),
        CalibrationCase("cal-v1-BEN-002", "hello zzz", "benign", "ordinary_coding", "s", "cal-v1"),
    ]
    r = cal.measure_calibration(cases, include_mutations=False, detector_fingerprint=None)
    m = r["metrics"]
    # ATT-001 BLOCK/TP, ATT-002 BLOCK/TP, ATT-003 ALLOW/FN, BEN-001 ALLOW/TN, BEN-002 BLOCK/FP
    assert (m["tp"], m["tn"], m["fp"], m["fn"]) == (2, 1, 1, 1)
    assert m["precision"] == 0.6667      # 2/(2+1)
    assert m["recall"] == 0.6667         # 2/(2+1)
    assert m["f1"] == 0.6667             # P == R
    assert m["false_positive_rate"] == 0.5   # 1/(1+1)
    assert m["false_negative_rate"] == 0.3333  # 1/(1+2)
    assert m["benign_over_refusal"] == 0.5  # BLOCK only (documented convention)


def test_measurement_rejects_single_class_and_empty(tmp_path, monkeypatch):
    from llm_security import guardrail_analyzer as ga

    def fake_analyse(text: str):
        return ga.Analysis("fp", 0.0, "ALLOW", ())

    monkeypatch.setattr(cal, "analyse", fake_analyse)
    only_attacks = [CalibrationCase(f"cal-v1-ATT-00{i}", "x", "attack", "f", "s", "cal-v1")
                    for i in range(1, 4)]
    with pytest.raises(CalibrationError):
        cal.measure_calibration(only_attacks, include_mutations=False, detector_fingerprint=None)
    with pytest.raises(CalibrationError):
        cal.measure_calibration([], include_mutations=False, detector_fingerprint=None)


def test_baseline_write_is_fail_closed(tmp_path, monkeypatch):
    from llm_security import guardrail_analyzer as ga

    def fake_analyse(text: str):
        return ga.Analysis("fp", 0.0, "ALLOW", ())

    monkeypatch.setattr(cal, "analyse", fake_analyse)
    only_attacks = [CalibrationCase("cal-v1-ATT-001", "x", "attack", "f", "s", "cal-v1")]
    with pytest.raises(CalibrationError):
        report = cal.measure_calibration(only_attacks, include_mutations=False,
                                         detector_fingerprint=None)
    with pytest.raises(CalibrationError):
        cal.write_measured_baseline({"status": "UNMEASURED", "metrics": {}}, tmp_path / "b.json")


# --------------------------------------------------------------------------
# 6. CI gate: three-layer separation, UNSET thresholds, UNMEASURED legacy
# --------------------------------------------------------------------------

def test_thresholds_are_unset_with_no_policy():
    t = load_release_thresholds(THRESHOLDS)
    assert t["status"] == "UNSET"
    assert t["policy"] is None
    assert t["schema"] == "lola.guardrail.release-threshold/v1"


def test_thresholds_reject_inconsistent_docs(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({
        "schema": "lola.guardrail.release-threshold/v1",
        "status": "UNSET",
        "policy": {"min_attack_recall": 0.9},
    }), encoding="utf-8")
    with pytest.raises(CalibrationError):
        load_release_thresholds(p)
    p.write_text(json.dumps({
        "schema": "wrong", "status": "UNSET", "policy": None,
    }), encoding="utf-8")
    with pytest.raises(CalibrationError):
        load_release_thresholds(p)


def test_legacy_baseline_stays_unmeasured():
    doc = json.loads(LEGACY.read_text(encoding="utf-8"))
    assert doc["status"] == "UNMEASURED"
    assert doc["dataset"]["total"] == 0


def test_gate_script_passes_and_fails_on_drift(tmp_path):
    gate = ROOT / "scripts" / "llm_security_calibration_gate.py"
    import subprocess
    ok = subprocess.run([sys.executable, str(gate)], capture_output=True, text=True, cwd=ROOT)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "GATE PASS" in ok.stdout

    # A detector change must make the drift check fail: identical metrics but a
    # different detector fingerprint => the committed baseline is invalid.
    committed = load_measured_baseline(BASELINE)
    fresh = _measure(_cases())
    fresh["detector"]["fingerprint"] = "deadbeef" * 8
    drift = baseline_drift(committed, fresh)
    assert drift == ["detector.fingerprint"]

    # A corpus change must fail too: same detector, different manifest.
    fresh2 = _measure(_cases())
    fresh2["corpus"]["sha256"] = "0" * 64
    assert "corpus.sha256" in baseline_drift(committed, fresh2)
