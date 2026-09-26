# Evidence Pipeline Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Lola APK and repository static-analysis outputs to the evidence/confidence engine while preserving existing scanner behavior.

**Architecture:** Add focused adapters that translate existing analyzer dictionaries into `Evidence` objects, then an orchestration layer that builds ledger findings/hypotheses and returns additive evidence analysis. Integrations are fail-open for the evidence layer only: original scan output remains available if evidence processing fails.

**Tech Stack:** Python 3, stdlib dataclasses/json/pathlib, existing `lola_evidence.py`, `lola_hypothesis.py`, pytest/unittest-compatible tests.

**Spec:** `docs/superpowers/specs/2026-09-26-evidence-pipeline-phase2.md`

## Global Constraints
- Preserve current APK/source scanner primary behavior.
- Evidence processing remains optional and analysis-only.
- Do not add Ghidra/PyGhidra in Phase 2.
- Do not fabricate evidence diversity or promote missing evidence.
- Keep provenance at entry+offset for APK observations and file+line for code observations where available.

## Review Focus
- Partial analyzer dictionaries must not crash normalization.
- Duplicate observations must not artificially inflate confidence.
- Missing evidence must remain explicit/UNKNOWN.
- Adapter/import failures must not suppress original scan output.
- Provenance locators must survive normalization and serialization.

---

### Task 1: Evidence adapters

**Files:**
- Create: `lola_evidence_adapters.py`
- Test: `tests/test_evidence_adapters.py`

**Interfaces:**
- Consumes: APK/code dictionaries.
- Produces: `apk_observations(data: dict) -> list[Evidence]`, `code_observations(report: dict) -> list[Evidence]`.

- [ ] Write failing tests for APK URLs, permissions/components, code syntax/definitions/imports, provenance, partial input and duplicate handling.
- [ ] Run focused tests and verify RED for missing adapter module/functions.
- [ ] Implement minimal normalization functions using `Evidence`.
- [ ] Run focused tests and verify GREEN.
- [ ] Commit adapter + tests.

### Task 2: Evidence pipeline orchestration

**Files:**
- Create: `lola_evidence_pipeline.py`
- Test: `tests/test_evidence_pipeline.py`

**Interfaces:**
- Consumes: target, normalized observations, optional expected evidence kinds/contradictions.
- Produces: `analyze_observations(target: str, observations: list[Evidence]) -> dict` and safe wrapper helpers.

- [ ] Write failing tests for ledger output, missing evidence, contradictions, UNKNOWN behavior and malformed input fallback.
- [ ] Verify RED.
- [ ] Implement minimal ledger/hypothesis orchestration.
- [ ] Verify focused GREEN.
- [ ] Commit pipeline + tests.

### Task 3: APK integration

**Files:**
- Modify: `analyze-apk.py`
- Test: `tests/test_evidence_integration.py`

**Interfaces:**
- Consumes: existing final APK analysis dictionary before JSON serialization.
- Produces: additive `evidenceAnalysis` object; original fields unchanged.

- [ ] Write failing integration test proving evidence output is additive and fallback preserves original analysis.
- [ ] Verify RED.
- [ ] Add guarded adapter/pipeline call immediately before analysis serialization.
- [ ] Verify focused GREEN.
- [ ] Commit APK integration.

### Task 4: Code-inspector integration

**Files:**
- Modify: `lola_code_inspector.py`
- Test: `tests/test_evidence_integration.py`

**Interfaces:**
- Consumes: existing inspection report.
- Produces: evidence-aware inspection result without changing existing mode keys.

- [ ] Write failing tests for code evidence provenance and compatibility with existing mode output.
- [ ] Verify RED.
- [ ] Add guarded evidence enrichment helper and expose it additively in applicable modes.
- [ ] Verify focused GREEN.
- [ ] Commit code-inspector integration.

### Task 5: Full verification and documentation

**Files:**
- Modify: `EVIDENCE_CORE.md`

- [ ] Run the repository's full Python test suite.
- [ ] Run syntax compilation/checks for modified Python files.
- [ ] Record any unrelated pre-existing failures explicitly rather than hiding them.
- [ ] Update evidence documentation with Phase 2 data flow and Phase 3 boundary.
- [ ] Re-run full verification after documentation/code cleanup.
- [ ] Open PR only with fresh verification evidence.