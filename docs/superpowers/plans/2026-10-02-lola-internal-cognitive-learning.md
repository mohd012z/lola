# Lola Internal Cognitive Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Release-3 internal evidence adapters, evidence-gradient verification, prediction-error episodes, and gated consolidation for Lola Kernel_AI / IN_AI.

**Architecture:** Extend the existing transport-independent cognitive fabric rather than creating a second stack. Internal sources normalize into KIP observations; hypothesis support and final verification become separate gates; durable trace events reconstruct episodes; only verified episodes may produce consolidation candidates.

**Tech Stack:** Python 3 standard library, dataclasses/enums, JSONL event store, unittest.

**Spec:** `docs/superpowers/specs/2026-10-02-lola-internal-cognitive-learning-design.md`

## Global Constraints

- Preserve KIP transport independence.
- Standard-library-only for Release 3.
- Deterministic parsing/scoring/validation before semantic model inference where practical.
- `SUPPORTED` must never implicitly mean `VERIFIED`.
- Permanent/consolidated learning requires verified evidence.
- Existing Release-1/2 behavior must remain regression-tested.

## Review Focus

- Replayed/duplicate observations must not count as independent corroboration; pinned in Task 2 tests.
- Two observations from the same source must not promote E2; pinned in Task 2 tests.
- Missing provenance must block verification; pinned in Task 3 tests.
- A failed validator or active epistemic fuse must block verification; pinned in Task 3 tests.
- PARTIAL/FAILED/ABORTED episodes must not create positive consolidation candidates; pinned in Task 5 tests.

---

### Task 1: Evidence Gradient and Internal Adapter Contract

**Files:**
- Create: `lola_cognitive_sources.py`
- Modify: `lola_cognitive_fabric.py`
- Test: `tests/test_cognitive_sources.py`

**Interfaces:**
- Consumes: existing `KIPEnvelope`.
- Produces: `EvidenceGrade`, `SourceRecord`, `InternalSourceAdapter.normalize(record, *, task_id, trace_id) -> KIPEnvelope`.

- [ ] **Step 1:** Add failing tests for E0-E4 serialization, provenance fields, and malformed record rejection.
- [ ] **Step 2:** Run `python -m unittest tests.test_cognitive_sources -v`; expect failures for missing interfaces.
- [ ] **Step 3:** Implement `EvidenceGrade`, `SourceRecord`, and reusable `InternalSourceAdapter` with deterministic normalization to observation envelopes.
- [ ] **Step 4:** Extend `KIPEnvelope` with evidence-grade/provenance fields while retaining backward-compatible defaults.
- [ ] **Step 5:** Run source tests and existing cognitive-fabric tests; expect PASS.
- [ ] **Step 6:** Commit `feat: add internal cognitive source adapters`.

### Task 2: Independent Corroboration Engine

**Files:**
- Create: `lola_cognitive_evidence.py`
- Test: `tests/test_cognitive_evidence.py`

**Interfaces:**
- Consumes: normalized KIP observations/evidence IDs.
- Produces: `CorroborationResult` and `corroborate(claim_key, observations, *, freshness_seconds=None) -> CorroborationResult`.

- [ ] **Step 1:** Add failing tests proving two independent sources can reach E2, same-source repeats cannot, duplicate event IDs cannot, and conflicting values are reported.
- [ ] **Step 2:** Run evidence tests; expect failure because corroboration interface is absent.
- [ ] **Step 3:** Implement deterministic evidence grouping, source independence, conflict reporting, and E2 promotion.
- [ ] **Step 4:** Run evidence tests; expect PASS.
- [ ] **Step 5:** Commit `feat: add independent evidence corroboration`.

### Task 3: Separate SUPPORTED from VERIFIED

**Files:**
- Modify: `lola_cognitive_fabric.py`
- Test: `tests/test_cognitive_fabric.py`

**Interfaces:**
- Consumes: `Hypothesis`, `CorroborationResult`, validator outcomes, `MetaController` state.
- Produces: `verify_hypothesis(task_id, hypothesis_id, *, corroboration, validators) -> dict[str, Any]`.

- [ ] **Step 1:** Change/add failing tests asserting `evaluate_hypothesis()` yields SUPPORTED without adding to `verified_claims`.
- [ ] **Step 2:** Add failing tests for verification success plus blocks for missing provenance, insufficient independent corroboration, validator failure, conflicts, and active epistemic fuse.
- [ ] **Step 3:** Run targeted tests; expect failures against current behavior.
- [ ] **Step 4:** Remove implicit verified promotion from `evaluate_hypothesis()` and implement explicit `verify_hypothesis()` gate.
- [ ] **Step 5:** Run targeted and full cognitive tests; expect PASS.
- [ ] **Step 6:** Commit `fix: separate supported and verified cognition`.

### Task 4: Prediction Error and Episode Reconstruction

**Files:**
- Create: `lola_cognitive_episode.py`
- Modify: `lola_cognitive_fabric.py`
- Test: `tests/test_cognitive_episode.py`

**Interfaces:**
- Consumes: trace-linked durable KIP events from `EventStore.replay()`.
- Produces: `PredictionDelta`, `Episode`, `record_prediction(...)`, `record_actual(...)`, `build_episode(events, trace_id) -> Episode`.

- [ ] **Step 1:** Add failing tests for exact prediction match, mismatch/delta, trace filtering, deterministic reconstruction, and unresolved prediction handling.
- [ ] **Step 2:** Run episode tests; expect missing-interface failures.
- [ ] **Step 3:** Implement prediction/result event helpers and deterministic episode builder.
- [ ] **Step 4:** Ensure prediction/actual events preserve task/correlation/trace/span ancestry.
- [ ] **Step 5:** Run episode tests and full cognitive suite; expect PASS.
- [ ] **Step 6:** Commit `feat: add prediction error episode reconstruction`.

### Task 5: Verified Consolidation Gate

**Files:**
- Create: `lola_cognitive_learning.py`
- Test: `tests/test_cognitive_learning.py`

**Interfaces:**
- Consumes: `Episode`.
- Produces: `LessonCandidate` and `candidate_from_episode(episode) -> LessonCandidate | None`.

- [ ] **Step 1:** Add failing tests proving VERIFIED episode creates a candidate while PARTIAL, FAILED, and ABORTED do not.
- [ ] **Step 2:** Add tests requiring supporting evidence IDs, applicability constraints, conflicts/counterexamples, and evidence-derived confidence fields.
- [ ] **Step 3:** Run learning tests; expect missing-interface failures.
- [ ] **Step 4:** Implement the minimal deterministic consolidation gate and candidate representation; do not mutate permanent memory.
- [ ] **Step 5:** Run learning and full cognitive suites; expect PASS.
- [ ] **Step 6:** Commit `feat: gate cognitive consolidation on verification`.

### Task 6: Integration, Documentation, and Regression Gate

**Files:**
- Modify: `COGNITIVE_FABRIC.md`
- Modify: `tests/test_cognitive_fabric.py` as required for integration coverage.

**Interfaces:**
- Consumes: Tasks 1-5 public interfaces.
- Produces: documented end-to-end internal flow and regression evidence.

- [ ] **Step 1:** Add an end-to-end test: internal source -> KIP observation -> hypothesis SUPPORTED -> independent corroboration -> validator -> VERIFIED -> episode -> lesson candidate.
- [ ] **Step 2:** Add negative end-to-end test where contradiction/failing validator prevents verification and consolidation.
- [ ] **Step 3:** Run targeted Release-3 tests; expect PASS.
- [ ] **Step 4:** Run repository unit-test discovery and Python compile checks used by CI; expect PASS.
- [ ] **Step 5:** Update `COGNITIVE_FABRIC.md` with Release-3 lifecycle and evidence gradient.
- [ ] **Step 6:** Inspect diff for dependency creep, accidental API breakage, or unverified claims.
- [ ] **Step 7:** Commit `docs: document verified cognitive learning flow`.
- [ ] **Step 8:** Check GitHub workflow/status for the resulting head SHA; report exact CI state without assuming success.
