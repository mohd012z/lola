# LLM Guardrail Evaluation V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, evidence-based evaluation for Lola's defensive LLM guardrail while preserving GuardPipeline as the sole ALLOW/REVIEW/BLOCK authority.

**Architecture:** A sanitized labelled fixture corpus feeds an evaluation harness that measures confusion metrics, mutation robustness, and threshold sensitivity. Evaluation and clustering remain observation-only; release_gate consumes aggregate metrics and fails closed on regression.

**Tech Stack:** Python 3.12, pytest 8.4.2, stdlib dataclasses/json/hashlib.

**Spec:** Stage-4 guardrail architecture on merge commit `4deebc89f66dab1e3c14cb8d7931e66c08cec9c6`.

## Global Constraints

- GuardPipeline remains the sole policy decision authority.
- Evaluation code must not execute corpus content or generate operational jailbreak payloads.
- Fixtures contain sanitized defensive examples only.
- Metrics and reports must not persist raw prompt text; use IDs/fingerprints and aggregate counts.
- Test dependencies remain pinned in `requirements-test.txt`.
- Every metric calculation must be deterministic.

## Review Focus

- Benign security discussions must not be counted as attacks solely because they mention guardrail terminology.
- Small formatting/case/whitespace changes should not cause unexplained metric collapse.
- Empty or single-class corpora must fail closed instead of producing misleading perfect scores.
- Threshold sweeps must not silently select a threshold or mutate production policy.
- Baseline comparison must detect both recall degradation and increased benign over-refusal.

---

### Task 1: Evaluation Corpus Schema

**Files:**
- Create: `llm_security/evaluation.py`
- Create: `tests/test_llm_security_evaluation.py`

**Interfaces:**
- Produces: `EvaluationCase`, `EvaluationReport`, `evaluate_cases(cases, pipeline=None)`.
- Report exposes TP/TN/FP/FN, precision, recall, F1, FPR, FNR and benign over-refusal.

- [ ] Write failing tests for balanced fixtures, missing attack controls, missing benign controls, and raw-text exclusion.
- [ ] Run `python -m pytest tests/test_llm_security_evaluation.py -v` and verify RED.
- [ ] Implement minimal deterministic evaluation harness.
- [ ] Run focused tests and verify GREEN.
- [ ] Commit `feat: add defensive guardrail evaluation harness`.

### Task 2: Mutation Robustness

**Files:**
- Create: `llm_security/mutations.py`
- Create: `tests/test_llm_security_mutations.py`

**Interfaces:**
- Produces: `Mutation`, `safe_mutations(text)` and `evaluate_mutations(cases, pipeline=None)`.
- Mutations are non-semantic formatting transformations only: case, whitespace, punctuation and duplicated spacing.

- [ ] Write failing tests proving deterministic mutation IDs and no policy authority.
- [ ] Verify RED.
- [ ] Implement minimal formatting-only mutations.
- [ ] Verify mutation tests GREEN and existing evaluation tests unchanged.
- [ ] Commit `feat: add deterministic guardrail mutation evaluation`.

### Task 3: Threshold Sweep

**Files:**
- Create: `llm_security/threshold_sweep.py`
- Create: `tests/test_llm_security_threshold_sweep.py`

**Interfaces:**
- Produces: `ThresholdPoint` and `sweep_cluster_thresholds(records, thresholds)`.
- Output is evidence only and must not contain `decision`, `action`, or automatic threshold selection.

- [ ] Write failing tests for deterministic ordering, invalid thresholds, and absence of decision authority.
- [ ] Verify RED.
- [ ] Implement sweep using existing `cluster_records`.
- [ ] Verify GREEN.
- [ ] Commit `feat: add evidence-only clustering threshold sweep`.

### Task 4: Versioned Baseline + Regression Comparison

**Files:**
- Create: `llm_security/baselines/guardrail-baseline-v1.json`
- Modify: `llm_security/regression_gate.py`
- Create: `tests/test_llm_security_baseline.py`

**Interfaces:**
- Produces: `load_baseline(path)` and baseline-compatible aggregate metrics.
- Regression gate consumes aggregates only; no raw fixture text is stored in baseline.

- [ ] Write failing tests for schema/version mismatch, recall regression, FPR regression and missing metrics.
- [ ] Verify RED.
- [ ] Implement strict baseline loader/comparison.
- [ ] Verify GREEN.
- [ ] Commit `feat: add versioned guardrail evaluation baseline`.

### Task 5: CI Evaluation Gate

**Files:**
- Modify: `.github/workflows/code-doctor.yml`
- Modify: `.github/workflows/toolchain-check.yml`

**Interfaces:**
- CI runs all `test_llm_security_*.py` modules through pytest and executes the evaluation regression check.

- [ ] Add CI assertions that evaluation modules execute and baseline comparison passes.
- [ ] Run complete local/CI-equivalent pytest suite.
- [ ] Require zero test failures and a successful toolchain status smoke check.
- [ ] Commit `ci: enforce guardrail evaluation regression gate`.

### Task 6: Verification

**Files:** none unless defects are discovered.

- [ ] Run `python -m pytest tests -v`.
- [ ] Confirm all prior 52 tests remain passing plus Stage-5 tests.
- [ ] Confirm reports contain no raw prompt payloads.
- [ ] Confirm clustering/evaluation objects expose no policy action/decision fields.
- [ ] Confirm Toolchain smoke check and LLM Guardrail CI both succeed on the same head SHA.
- [ ] Open Stage-5 PR only after the branch is internally consistent.
