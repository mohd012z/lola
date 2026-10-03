# LOLA Security Intelligence & Hybrid Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the defensive jailbreak prototype into enforceable cross-function trust/provenance, action authorization, Evidence Core, Hybrid-C memory, and typed intelligence services.

**Architecture:** Keep hostile material fully inspectable while propagating provenance/taint through analysis. Deterministic application code owns capabilities, privileged actions and global-memory promotion; AI components only propose findings, knowledge, methods, patches and actions.

**Tech Stack:** Python 3 stdlib-first, unittest, JSON/JSONL, existing LOLA scripts.

**Spec:** `docs/superpowers/specs/2026-09-29-lola-security-intelligence-memory-design.md`

## Global Constraints

- Content is data, not authority.
- Imported/artifact/model content cannot mint trust or capabilities.
- READ analysis remains available for hostile content.
- MEMORY_WRITE and SIDE_EFFECT cross deterministic authorization boundaries.
- Hybrid-C: raw/project memory is isolated from validated global knowledge.
- Global promotion requires provenance, evidence, contradiction checking and Memory Firewall approval.
- Existing analyzers remain callable during migration.
- Preserve stdlib-only compatibility for the shared security core.

## Review Focus

1. Unicode/encoded instruction content must preserve source provenance and must not become trusted after normalization.
2. Derived AI summaries of untrusted artifacts must retain derived-untrusted taint.
3. A model-produced authorization phrase must not satisfy an Action Firewall capability requirement.
4. Conflicting memories must coexist as disputed/versioned records rather than silently overwrite one another.
5. Evidence-write failure must prevent a privileged operation from claiming auditable completion.

---

### Task 1: Typed Security Contracts

**Files:**
- Create: `lola_security_contracts.py`
- Modify: `lola_security.py`
- Test: `tests/test_lola_security_contracts.py`

**Interfaces:**
- Produces: `ArtifactContext`, `SecurityFinding`, `Capability`, `ActionRequest`, `Taint`, extended `TrustEnvelope` compatibility helpers.

- [ ] Write failing tests for artifact identity, parent provenance, capability enumeration and taint inheritance.
- [ ] Run `python -m unittest tests.test_lola_security_contracts -v`; expect failure because contracts do not exist.
- [ ] Implement the minimal frozen dataclasses/enums and compatibility conversion in `lola_security.py`.
- [ ] Run the test module and existing `tests/test_lola_security.py`; expect PASS.
- [ ] Commit `feat: add typed LOLA security contracts`.

### Task 2: Provenance and Taint Propagation

**Files:**
- Create: `lola_provenance.py`
- Test: `tests/test_lola_provenance.py`

**Interfaces:**
- Consumes: `ArtifactContext`, `Taint` from Task 1.
- Produces: `derive_artifact(parent, payload, transformation, source_id) -> ArtifactContext`; `ProvenanceGraph`.

- [ ] Write failing tests proving parent hash/ID lineage, deterministic content hashes and inherited `DERIVED_FROM_UNTRUSTED` taint.
- [ ] Run tests; verify RED.
- [ ] Implement derivation and an in-memory provenance DAG with JSON-serializable records.
- [ ] Run tests; expect PASS.
- [ ] Commit `feat: add provenance and taint propagation`.

### Task 3: Capability Policy and Action Firewall

**Files:**
- Create: `lola_action_firewall.py`
- Modify: `lola_security.py`
- Test: `tests/test_lola_action_firewall.py`

**Interfaces:**
- Consumes: `ActionRequest`, `Capability`, `TrustEnvelope`.
- Produces: `authorize(request, envelope, granted_capabilities) -> SecurityDecision`.

- [ ] Write failing tests: hostile READ allowed read-only; missing capability denies; model text claiming authorization still denies; explicit application capability permits trusted report write.
- [ ] Verify RED.
- [ ] Implement deterministic capability checks and map legacy `DecisionEngine` calls through the firewall where compatible.
- [ ] Run new + legacy security tests; expect PASS.
- [ ] Commit `feat: enforce capability action firewall`.

### Task 4: Evidence Core Ledger

**Files:**
- Create: `lola_evidence.py`
- Test: `tests/test_lola_evidence.py`

**Interfaces:**
- Consumes: artifact/provenance IDs, `SecurityDecision`, method/memory IDs.
- Produces: `EvidenceLedger.append(event)`, `trace(trace_id)`, JSONL persistence.

- [ ] Write failing tests for append/read, immutable event IDs, source-to-decision lineage and corrupt-record rejection.
- [ ] Verify RED.
- [ ] Implement append-only JSONL ledger with canonical event hashing.
- [ ] Run tests; expect PASS.
- [ ] Commit `feat: add evidence core ledger`.

### Task 5: Static Analyzer Adapters

**Files:**
- Modify: `analyze-apk.py`
- Modify: `analyze-code.py`
- Modify: `android_code_reader.py`
- Create: `lola_analyzer_adapter.py`
- Test: `tests/test_analyzer_security_adapters.py`

**Interfaces:**
- Consumes: provenance + TrustEnvelope.
- Produces: analyzer findings paired with artifact/provenance IDs without changing legacy CLI output contracts.

- [ ] Write failing adapter tests using benign and instruction-bearing extracted strings.
- [ ] Verify RED.
- [ ] Add compatibility adapter and minimally wire static analyzers at ingestion/finding boundaries.
- [ ] Verify hostile strings remain analyzable and retain untrusted provenance.
- [ ] Run relevant existing tests plus adapter tests; expect PASS.
- [ ] Commit `feat: propagate trust through static analyzers`.

### Task 6: Network and Runtime Boundaries

**Files:**
- Modify: `analyze-network.py`
- Modify: `apk_runtime_monitor.py`
- Test: `tests/test_external_boundary_security.py`

**Interfaces:**
- Consumes: analyzer adapter, action firewall, Evidence Ledger.
- Produces: untrusted network/runtime evidence records; no authority escalation.

- [ ] Write failing tests showing response/runtime text cannot create capabilities or authorize side effects.
- [ ] Verify RED.
- [ ] Wire external observations through trust/provenance envelopes and evidence events.
- [ ] Run tests; expect PASS.
- [ ] Commit `feat: secure network and runtime boundaries`.

### Task 7: Hybrid-C Memory Store

**Files:**
- Create: `lola_memory.py`
- Test: `tests/test_lola_memory.py`

**Interfaces:**
- Produces: `MemoryRecord`, `ProjectMemoryStore`, `GlobalMemoryStore`, lifecycle enum.

- [ ] Write failing tests for project isolation, lifecycle transitions, duplicate merge by proposition/hash, and conflict preservation.
- [ ] Verify RED.
- [ ] Implement project/global stores with versioned JSON persistence and no direct project-to-global write path.
- [ ] Run tests; expect PASS.
- [ ] Commit `feat: add hybrid project and global memory stores`.

### Task 8: Memory Promotion, Correction and Revocation

**Files:**
- Create: `lola_memory_governance.py`
- Test: `tests/test_memory_governance.py`

**Interfaces:**
- Consumes: project memory, Evidence Ledger, action firewall.
- Produces: `evaluate_promotion(record_id, evidence_ids)`, `supersede(old_id, new_record)`, `revoke(record_id, reason)`.

- [ ] Write failing tests for insufficient evidence HOLD, contradiction DISPUTED, validated promotion, supersession lineage and model-text authorization rejection.
- [ ] Verify RED.
- [ ] Implement promotion gate with inspectable confidence dimensions rather than one opaque model score.
- [ ] Run tests; expect PASS.
- [ ] Commit `feat: govern memory promotion and correction`.

### Task 9: Typed Intelligence Bus

**Files:**
- Create: `lola_intelligence_bus.py`
- Test: `tests/test_intelligence_bus.py`

**Interfaces:**
- Produces typed request/result dataclasses for analysis, study, method, code, evidence, memory and action proposals.

- [ ] Write failing serialization/validation tests, including taint/evidence/trace preservation across hops.
- [ ] Verify RED.
- [ ] Implement typed envelopes and handler registry; reject treating arbitrary free-form text as a bus command.
- [ ] Run tests; expect PASS.
- [ ] Commit `feat: add typed intelligence bus`.

### Task 10: Study, Analyze and FalseTrue Services

**Files:**
- Create: `lola_study.py`
- Create: `lola_analysis.py`
- Create: `lola_falsetrue.py`
- Test: `tests/test_intelligence_services.py`

**Interfaces:**
- Consumes: Intelligence Bus, project/global memory, Evidence Ledger.
- Produces bounded study candidates, evidence-state analysis and falsification outcomes.

- [ ] Write failing tests for bounded recursion, UNKNOWN on insufficient evidence, counter-evidence preservation and candidate-not-global behavior.
- [ ] Verify RED.
- [ ] Implement deterministic orchestration shells; model adapters remain optional proposal providers.
- [ ] Run tests; expect PASS.
- [ ] Commit `feat: add study analysis and falsification services`.

### Task 11: Method Knowledge

**Files:**
- Create: `lola_methods.py`
- Test: `tests/test_lola_methods.py`

**Interfaces:**
- Produces versioned `MethodRecord`, outcome recording and context-aware method selection.

- [ ] Write failing tests for success/failure history, false-positive history, versioning and context compatibility outranking raw success percentage.
- [ ] Verify RED.
- [ ] Implement method registry and evidence-linked outcome updates.
- [ ] Run tests; expect PASS.
- [ ] Commit `feat: add evidence-backed method knowledge`.

### Task 12: Coder Proposal Pipeline

**Files:**
- Create: `lola_coder.py`
- Test: `tests/test_lola_coder.py`

**Interfaces:**
- Consumes: repository context envelopes, validated memory/methods, Action Firewall.
- Produces: `PatchProposal`; repository mutation remains separate.

- [ ] Write failing tests proving repository comments cannot authorize writes and coder output has proposal-only capability.
- [ ] Verify RED.
- [ ] Implement patch proposal metadata, validation result hooks and evidence linkage without an unrestricted repository writer.
- [ ] Run tests; expect PASS.
- [ ] Commit `feat: add guarded coder proposal pipeline`.

### Task 13: Output Guard and Reporting

**Files:**
- Create: `lola_output_guard.py`
- Modify: `build-apk-report.py`
- Test: `tests/test_output_guard.py`

**Interfaces:**
- Produces escaped/sanitized report fields while retaining raw hashes/provenance separately.

- [ ] Write failing tests for HTML/script-like artifact strings and provenance-preserving rendered findings.
- [ ] Verify RED.
- [ ] Implement output guard and wire report rendering boundary.
- [ ] Run tests; expect PASS.
- [ ] Commit `feat: guard LOLA report output`.

### Task 14: Adversarial and Benign Regression Governance

**Files:**
- Modify: `jailbreak_eval.py`
- Create: `tests/fixtures/jailbreak/README.md`
- Create: `tests/test_jailbreak_regression.py`

**Interfaces:**
- Consumes detector/security APIs.
- Produces precision/recall-style counts, false-positive/negative fixtures and authorization-boundary regression results.

- [ ] Write failing tests for role override, authority spoofing, policy replacement, reevaluation suppression, tool coercion, persistence, benign quoted discussion and Unicode variants.
- [ ] Verify RED.
- [ ] Extend evaluator categories/features without making corpus text authoritative.
- [ ] Run regression suite; expect PASS.
- [ ] Commit `test: add jailbreak and benign regression governance`.

### Task 15: Cross-Function Verification and Compatibility

**Files:**
- Create: `tests/test_lola_security_integration.py`
- Modify: `LOLA_SECURITY_INTEGRATION.md`

**Interfaces:**
- Consumes all prior components.
- Produces end-to-end proof from hostile artifact ingestion through analysis/evidence/memory proposal to denied unauthorized side effect and permitted read-only inspection.

- [ ] Write integration tests for the five Review Focus cases and legacy analyzer invocation compatibility.
- [ ] Run them first and verify any uncovered integration defect is RED.
- [ ] Fix only defects exposed by the integration tests.
- [ ] Run `python -m unittest discover -s tests -v`; expect full PASS.
- [ ] Update integration documentation with final module map and commands.
- [ ] Commit `test: verify LOLA cross-function security architecture`.

## Completion Gate

Before merge, verify:

- full unittest discovery is green;
- existing analyzer entry points still operate;
- hostile material remains readable;
- no imported/model content can mint capabilities;
- project memory cannot bypass promotion governance;
- Evidence Core can trace source -> transformation -> finding -> decision/result;
- output rendering escapes active artifact markup;
- adversarial and benign fixtures both pass expected classifications;
- PR diff contains no credentials or generated analysis artifacts.
