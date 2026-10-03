# LOLA Security, Intelligence & Hybrid AI Memory — Design Specification

Date: 2026-09-29
Status: Design for review
Branch: feature/jailbreak-evaluation-harness

## 1. Purpose

LOLA must inspect hostile or instruction-bearing APK resources, DEX strings, source code, documents, network responses, runtime observations, model output and adversarial prompt corpora without allowing those artifacts to acquire authority over LOLA.

The design extends the existing defensive jailbreak evaluation and `lola_security.py` prototype into a cross-function architecture for `/study`, `/analyze`, `/coder`, `/methode`, `/falsetrue`, Evidence Core and Hybrid AI Memory.

Core invariant:

> Content is data, not authority.

A model may propose findings, memories, methods, patches and actions. Deterministic application code owns trust, authorization, capability grants, persistence and privileged side effects.

## 2. Scope

This specification covers:

- trust and taint propagation;
- artifact provenance;
- prompt/instruction attack detection;
- deterministic policy and action authorization;
- hybrid project/global AI memory;
- memory promotion, correction and revocation;
- intelligence-bus contracts;
- `/study`, `/analyze`, `/coder`, `/methode`, `/falsetrue`;
- Evidence Core integration;
- output/report boundaries;
- adversarial and benign regression evaluation;
- phased migration of existing LOLA analyzers.

It does not make an LLM an authorization engine and does not permit imported adversarial content to modify LOLA policy.

## 3. Architectural Planes

LOLA is separated into five planes.

### 3.1 Security Plane

Owns canonicalization, trust, taint, capabilities, policy, decisions, memory-write gates and the Action Firewall.

### 3.2 Evidence Plane

Owns source identity, hashes, provenance DAGs, transformations, findings, decisions, replay metadata and audit records.

### 3.3 Memory Plane

Owns project memory, validated global knowledge, lifecycle states, confidence dimensions, contradiction tracking, expiry and promotion.

### 3.4 Intelligence Plane

Contains `/study`, `/analyze`, `/coder`, `/methode` and `/falsetrue`. Intelligence components may reason and propose; they do not mint trust or capabilities.

### 3.5 Evaluation Plane

Runs malicious corpus, benign near-miss, mutation, memory-poisoning, tool-boundary and cross-function regression tests.

## 4. Common Data Contracts

### ArtifactContext

Carries artifact identity, project, source type, source URI/path, parent artifact, content hash, transformation chain and timestamps.

### TrustEnvelope

Carries payload plus source identity, trust state, taints, executable state and provenance reference. Derived artifacts inherit taint unless a deterministic validation step explicitly changes state.

### SecurityFinding

A detector result with detector ID/version, category, evidence references, confidence dimensions and matched structural features.

### SecurityDecision

One of `ALLOW`, `ALLOW_READ_ONLY`, `QUARANTINE`, `REVIEW`, `DENY`, plus deterministic reasons and the evaluated action.

### ActionRequest

Contains action name, action class, requested capabilities, scope, target, authorization source and trace ID.

### EvidenceEvent

Records source, transformation, findings, proposed action, policy decision, result and engine versions.

### MemoryRecord

Contains knowledge ID/version, project scope, type, proposition, source/evidence IDs, confidence dimensions, validation state, support/counter-evidence, method history, timestamps, expiry and supersession links.

## 5. Trust and Taint

Default external/artifact states are untrusted. Examples include APK content, source comments, imported prompts, websites, network responses and runtime observations.

Derived data retains source taint:

`APK -> classes.dex -> extracted string -> decoded text -> AI summary`

The AI summary is `DERIVED_FROM_UNTRUSTED`; summarization does not make it authoritative.

Policy/configuration installed by the application may be trusted metadata, but trust must never be inferred from artifact/model text.

## 6. Capabilities and Action Firewall

Capabilities are granted by application policy, never by prompt content. Initial capability vocabulary:

- `READ_ARTIFACT`
- `DECODE_LOCAL`
- `TRANSFORM_LOCAL`
- `WRITE_LOCAL_REPORT`
- `MEMORY_WRITE_PROJECT`
- `MEMORY_PROMOTE_GLOBAL`
- `NETWORK_REQUEST`
- `EXTERNAL_ACTION`

Action classes:

- READ — normally inspectable even when hostile;
- TRANSFORM — local deterministic transformation, subject to scope/quarantine rules;
- MEMORY_WRITE — persistence boundary;
- SIDE_EFFECT — external or privileged state change.

All MEMORY_WRITE and SIDE_EFFECT actions pass the Action Firewall. Model output cannot serve as proof of authorization.

## 7. Guardrail Ensemble

The detector stack is layered:

1. canonicalization and encoding/Unicode checks;
2. deterministic signatures;
3. fuzzy/obfuscation features;
4. structural instruction detection;
5. semantic attack-family classification;
6. hierarchy/authority-conflict detection;
7. persistence and memory-poisoning detection;
8. tool/action-intent detection;
9. cross-turn behavioral evaluation;
10. output boundary checks.

Required attack families include role override, authority spoofing, policy replacement, hierarchy inversion, refusal suppression, safety-reevaluation suppression, tool coercion, persistence, context poisoning, memory poisoning, output manipulation and multi-stage escalation.

No individual detector is the policy engine. Detector disagreement is retained as evidence and may result in `REVIEW` rather than blind averaging.

## 8. Hybrid AI Memory (Option C)

### 8.1 Project Memory

Stores raw observations, hypotheses, project evidence and project-specific derived knowledge. It may retain untrusted-source material as data with provenance.

### 8.2 Global Validated Memory

Contains only promoted, validated cross-project knowledge such as proven analysis methods, structural code patterns, attack families, correction lessons and stable domain facts.

Raw external content is never promoted as governing instruction.

### 8.3 Lifecycle

`OBSERVED -> CANDIDATE -> VALIDATING -> VALIDATED -> PROMOTED`

Alternative states:

- `HOLD`
- `DISPUTED`
- `FALSIFIED`
- `SUPERSEDED`
- `REVOKED`
- `EXPIRED`

Old records are not silently overwritten. Supersession creates a versioned lineage.

### 8.4 Confidence

Do not store one opaque AI probability. Preserve dimensions:

- evidence quality;
- replication count;
- source diversity;
- freshness;
- contradiction penalty;
- method reliability.

A presentation score may be computed from these dimensions, but the dimensions remain inspectable.

### 8.5 Promotion Gate

Global promotion requires:

- intact provenance;
- sufficient supporting evidence;
- contradiction search;
- scope check;
- injection/memory-poisoning check;
- validation threshold;
- deterministic Memory Firewall decision.

No model receives an unrestricted `write_global_memory` capability.

## 9. Intelligence Bus

Agents/components exchange typed messages instead of treating free-form model text as commands.

Message families:

- `AnalysisRequest` / `AnalysisResult`
- `StudyRequest` / `KnowledgeCandidate`
- `MethodRequest` / `MethodCandidate`
- `CodeRequest` / `PatchProposal`
- `EvidenceRequest` / `EvidenceResult`
- `MemoryQuery` / `MemoryCandidate`
- `ActionProposal` / `SecurityDecision`

Common envelope fields include trace ID, project ID, source IDs, trust, taints, capability set, evidence IDs, parent trace and schema version.

## 10. `/study`

Pipeline:

`collect -> normalize -> classify -> extract concepts -> compare memory -> hypothesis -> cross-check -> falsify -> evidence -> candidate memory`

Study recursion is bounded by configurable maximum depth, hypotheses, tool calls, retries and memory writes.

Study learns structural patterns from adversarial material; it does not adopt adversarial instructions as policy.

## 11. `/analyze`

Combines static findings, runtime observations, project memory, validated global knowledge and cross-source evidence.

Analysis outputs evidence states such as `SUPPORTED`, `PROBABLE`, `UNCERTAIN`, `CONTRADICTED` and `UNKNOWN`. These states are evidence descriptions, not authorization decisions.

## 12. `/falsetrue`

Every important hypothesis can be subjected to:

- supporting-evidence search;
- counter-evidence search;
- alternative hypothesis generation;
- independent re-analysis;
- missing-evidence identification.

Outcomes include `SUPPORTED`, `DISPUTED`, `FALSIFIED` and `UNKNOWN`.

## 13. `/methode`

Methods are versioned first-class records with purpose, prerequisites, ordered steps, compatible artifact types, evidence requirements, success/failure history, false-positive history, confidence dimensions and version.

Method selection considers artifact/context compatibility and historical evidence. A high historical success percentage alone is insufficient.

## 14. `/coder`

Coder flow:

`repository context -> TrustEnvelope -> validated code/method memory -> PatchProposal -> static checks -> tests -> security tests -> diff-scope check -> EvidenceEvent -> authorized repository action`

Repository files, comments, README content, issues and generated text are treated as project/external context, not authority.

Coder has proposal capability by default. Repository writes remain a separately authorized action boundary.

Successful patches create outcome evidence. Repeated validated outcomes may update method reliability; a model assertion that a patch works is insufficient.

## 15. Evidence Core

Evidence Core stores a provenance DAG:

`source -> transformation -> finding -> inference -> proposed action -> policy decision -> result`

Required properties:

- content hashes;
- parent/child artifact relationships;
- detector and engine versions;
- memory IDs/versions consulted;
- method IDs/versions used;
- action decision reasons;
- replay metadata.

This supports future `/trace`, `/why`, `/source`, `/provenance`, `/decision` and `/replay` interfaces.

## 16. Output Boundary

Artifact/model content is escaped or sanitized before HTML/Markdown/report rendering. Report rendering cannot convert analyzed markup into executable authority or active content.

Output sanitization is separate from input detection and action authorization.

## 17. Existing LOLA Migration

Phase A — Core contracts

- evolve `lola_security.py` into focused modules without breaking its compatibility surface;
- introduce ArtifactContext, findings, capabilities and action requests;
- add Evidence Core event schema.

Phase B — Static analyzers

- `analyze-apk.py`
- `analyze-code.py`
- `android_code_reader.py`

Wrap extracted material with provenance/trust envelopes and preserve taint through transformations.

Phase C — Dynamic/external boundaries

- `analyze-network.py`
- `apk_runtime_monitor.py`

Network/runtime observations remain evidence inputs and cannot authorize actions.

Phase D — Output/reporting

- `build-apk-report.py`

Use output guard and evidence rendering.

Phase E — Intelligence

Implement typed `/study`, `/analyze`, `/falsetrue`, `/methode`, then `/coder`.

Phase F — Hybrid memory

Add project store, promotion gate, global validated store, contradiction/supersession handling and confidence dimensions.

Phase G — Regression governance

Add malicious and benign corpora, mutation tests, memory-poison tests, action-boundary tests and CI regression thresholds.

## 18. Evaluation Metrics

Track at minimum:

- attack detection recall;
- precision;
- false-positive rate;
- false-negative rate;
- hierarchy preservation rate;
- indirect-injection detection rate;
- memory-poisoning prevention rate;
- unauthorized side-effect rate;
- output leakage/rendering violations;
- cross-function policy consistency;
- regression escape rate.

Benign near-miss fixtures are mandatory so the system does not become a keyword blocker.

## 19. Failure Handling

- Missing provenance: prevent global promotion; permit local read-only analysis where safe.
- Detector disagreement: preserve all findings and route high-impact actions to review.
- Memory conflict: mark disputed; do not overwrite either proposition.
- Stale knowledge: decay freshness and require revalidation where appropriate.
- Policy-engine failure: fail closed for privileged actions; preserve forensic read access.
- Evidence-write failure: privileged action must not claim auditable completion.
- AI/model failure: deterministic security and evidence components remain operational.

## 20. Compatibility

Existing LOLA analyzers remain callable during migration. Compatibility adapters translate legacy analyzer inputs/outputs into the new contracts. Security enforcement is mandatory at privileged boundaries; envelope/provenance propagation is mandatory for migrated components.

Pure offline read analysis remains available even for hostile content.

## 21. Acceptance Criteria

The architecture is complete when:

1. all migrated artifact sources carry provenance and trust state;
2. derived artifacts retain taint lineage;
3. analyzed content cannot mint trust/capabilities;
4. privileged actions pass deterministic authorization;
5. project memory cannot directly promote itself globally;
6. every promoted memory has evidence and validation lineage;
7. contradictions can dispute/supersede existing knowledge without erasing history;
8. coder output is a proposal until separately authorized;
9. Evidence Core can explain source, method, memory and decision lineage;
10. adversarial and benign regression suites measure security and usability together.

## 22. Implementation Principle

LOLA should become more capable at reading hostile material, not less capable. Guardrails constrain authority, persistence and side effects—not legitimate forensic inspection.
