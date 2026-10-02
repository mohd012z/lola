# Lola Episode Engine v2 — Governed Consolidation Design

## Goal
Extend the green Release-3 cognitive checkpoint into a provenance-preserving episodic learning system that can reconstruct why a decision changed, measure which probes were useful, compare related episodes, retain counterexamples, and promote only well-supported recurring patterns into separately addressable semantic or procedural memory candidates.

## Evidence base and design synthesis
The design adopts five complementary ideas from current agent-memory research without treating any one architecture as authoritative:

1. **Recurrence-triggered consolidation**: delay expensive semantic extraction until related experiences recur, rather than consolidating every interaction eagerly (RecMem, ACL Findings 2026).
2. **Episodic graph + semantic distillation**: retain an episodic association graph and distill densely supported patterns into a separate semantic layer (HeLa-Mem, ACL 2026).
3. **Context reconstruction over destructive preprocessing**: preserve enough raw sequential context to reconstruct an episode rather than relying only on lossy summaries/embeddings (E-mem, ICML 2026).
4. **Encoding/consolidation separation**: isolate fast event progression from stable long-term knowledge to reduce transient-noise interference (GAM, ACL 2026).
5. **Governed consolidation**: promotion quality and governance are separate concerns; consolidation must be reversible, auditable, provenance-preserving, and resistant to bad/poisoned episodes rather than relying on a scalar confidence alone (recent 2026 consolidation research).

## Memory planes

```text
M0 RAW LEDGER       immutable/replayable KIP events
      |
      v
M1 EPISODIC         reconstructed bounded experiences
      |
      v
M1X CROSS-EPISODE   recurrence, contrast, counterexamples, transfer
      |
      v
M2 SEMANTIC         candidate reusable facts/principles
M3 PROCEDURAL       candidate reusable diagnostic/action procedures
```

M2/M3 are derived projections. Consolidation MUST NOT rewrite or erase M0/M1 evidence.

## Episode schema v2
An episode extends the current trace reconstruction with:
- `episode_id`, `task_id`, `trace_id`, objective, goal/subgoal/phase boundaries;
- ordered raw event references;
- observations and evidence IDs;
- hypothesis lifecycle and revision chain;
- predictions and structured actual results;
- prediction deltas;
- probes/actions and their costs;
- unknown-set before/after each probe;
- information-gain record;
- contradictions and resolution state;
- verification results and validators;
- evidence-lineage DAG references;
- unresolved unknowns;
- outcome: VERIFIED, PARTIAL, FAILED, ABORTED, FALSIFIED, SUPERSEDED;
- applicability/context fingerprint.

## Episode boundaries
Boundary signals are explicit where possible and heuristic only as fallback.

Priority:
1. explicit task/episode start/end;
2. goal/subgoal transition;
3. verification/final outcome boundary;
4. trace-root transition;
5. configured semantic/temporal fallback.

Heuristic segmentation can propose a boundary but cannot silently delete or merge raw events. The original event IDs remain available for replay.

## Evidence Lineage DAG
Every material derived claim has lineage edges to its inputs.

Node types:
- EVENT
- OBSERVATION
- DERIVATION
- HYPOTHESIS
- PREDICTION
- ACTUAL
- VERIFICATION
- EPISODE
- LESSON_CANDIDATE

Edge types:
- OBSERVED_FROM
- DERIVED_FROM
- SUPPORTS
- CONTRADICTS
- PREDICTS
- TESTED_BY
- REVISED_BY
- VERIFIED_BY
- CONSOLIDATED_FROM
- SUPERSEDES

Invariant: no E1/E2/E3 or consolidated candidate may exist without a traversable path back to at least one source observation/event.

## Independence domains
Distinct source IDs are not sufficient evidence of independence. Each evidence record may carry:
- `source_id`
- `channel_id`
- `origin_id`
- `artifact_hash`
- `method_id`

Two confirmations share a dependency domain when they originate from the same underlying artifact/event/channel in a way that makes correlated failure plausible. Effective corroboration counts independent domains, not raw message count.

Examples:
- two parsers reading one identical build log: one origin domain;
- build log + independently executed runtime observation: potentially two domains;
- replayed duplicate event: zero additional independence.

## Revision chain
Hypotheses are append-only revisions rather than overwritten text.

```text
H1@r0 PROPOSED
 -> evidence/probe
H1@r1 SUPPORTED
 -> contradiction
H1@r2 REVISED
 -> validator
H1@r3 VERIFIED
```

Each revision records trigger event/evidence IDs, previous revision ID, changed predictions/assumptions, and reason. Falsified revisions remain queryable.

## Information gain accounting
For each probe/action, Episode Engine records measurable change rather than an LLM self-rating.

Primary deterministic signal:
`resolved_unknowns = unknowns_before - unknowns_after`

Additional fields:
- contradictions resolved/introduced;
- hypotheses eliminated/supported;
- acquisition cost (normalized tool/time/token budget where available);
- evidence grade gained;
- validator progress.

A bounded utility metric may rank probes, but raw component values remain stored so ranking policy can change without rewriting history.

## Cross-episode engine
Cross-episode analysis operates over M1 without mutating episodes.

It produces clusters/sets for:
- recurrence: materially similar context + pattern;
- contrast: similar context but different outcome;
- counterexample: episode incompatible with candidate rule;
- transfer: different context where candidate relation/procedure still succeeds;
- supersession: newer evidence invalidates or narrows an older candidate.

Similarity is a retrieval aid, not proof. Promotion depends on evidence and validation gates.

## Recurrence gate
A single verified success remains episodic knowledge only.

A recurrence candidate requires configurable repeated support across effective independence domains. No universal fixed N is claimed as epistemically optimal; thresholds are policy and must be testable/configurable.

The gate records:
- supporting episode IDs;
- effective independent domains;
- context similarity/diversity;
- observed failure/counterexample count;
- freshness/time spread;
- unresolved contradictions.

## Counterexample and falsification gate
Before semantic/procedural promotion, search relevant M1 episodes for:
- same trigger/context with different outcome;
- failed/falsified procedures;
- conflicting direct evidence;
- boundary-condition violations.

Counterexamples do not automatically delete a pattern. They may:
- reject it;
- narrow applicability constraints;
- lower it back to episodic-only;
- supersede an earlier candidate.

## Transfer gate
A candidate general principle/procedure should be tested outside the exact originating episode cluster where practical. Transfer results are stored as new episodes, not injected as synthetic evidence.

## Consolidation outputs
### Semantic candidate (M2)
Contains:
- proposition/principle;
- applicability constraints;
- supporting/counterexample episode IDs;
- lineage root IDs;
- effective independence domains;
- verification/transfer state;
- version and supersession links;
- status: CANDIDATE, VERIFIED_CANDIDATE, REJECTED, SUPERSEDED.

### Procedural candidate (M3)
Contains:
- trigger/preconditions;
- ordered steps/probes;
- expected intermediate observations;
- stop/fallback conditions;
- validators;
- applicability constraints;
- supporting/failure episodes;
- lineage and version metadata.

Executable authority is separate from procedural memory. A stored procedure does not automatically gain permission to execute actions.

## Consolidation governor
Promotion evaluates separate dimensions rather than one opaque confidence score:
1. provenance completeness;
2. effective independence;
3. recurrence;
4. contradiction/counterexample state;
5. reproduction/validator results;
6. transfer evidence where required;
7. applicability specificity;
8. reversibility/auditability.

Failure of governance requirements blocks promotion even if a quality heuristic is high.

## Retrieval
Retrieval order should preserve fidelity:
1. current task/HOT state;
2. verified semantic/procedural candidates matching applicability;
3. relevant episodes;
4. raw lineage events when verification/detail is needed.

For high-impact decisions, Kernel can require lineage expansion before using a consolidated candidate.

## Retention and forgetting
Release v2 does not physically delete M0 evidence automatically. Forgetting initially means retrieval de-prioritization, supersession, or retention-policy eligibility. Any later destructive retention policy requires a separate design because deletion affects audit/replay guarantees.

## Kernel_AI / IN_AI responsibilities
Kernel_AI owns boundaries, IDs, event durability, lineage invariants, independence calculation, verification gates, consolidation governance, retrieval policy, and execution permissions.

IN_AI may propose episode labels, hypotheses, abstractions, similarity candidates, counterexamples, and applicability constraints. These remain E3/E4 outputs until deterministic/evidence gates validate them. IN_AI cannot self-promote memory.

## Failure modes explicitly covered
- one-shot overlearning;
- duplicate/replayed evidence inflation;
- two tools sharing one underlying origin masquerading as independence;
- summary drift from raw context;
- successful outcome incorrectly attributed to preceding action;
- stale lesson used outside applicability;
- contradictory episodes hidden by averaging;
- failed episode discarded instead of retained as counterexample;
- consolidated candidate silently rewritten;
- model-generated reflection becoming circular evidence;
- high quality score bypassing governance;
- transfer failure after apparent in-cluster success.

## Implementation phases
### V2-A Episode enrichment
Evidence Lineage DAG, independence domains, revision chain, information-gain records.

### V2-B Cross-episode analysis
Recurrence sets, contrast/counterexample discovery, context fingerprints.

### V2-C Governed consolidation
Semantic/procedural candidate schemas, promotion gates, supersession/reopening.

### V2-D Retrieval and regression
Applicability-aware retrieval, lineage expansion, replay/regression tests, metrics.

## Acceptance criteria
1. Existing green Release-3 tests remain green.
2. Every derived/consolidated object can trace to raw event/evidence lineage.
3. Same-origin evidence cannot inflate independence.
4. Hypothesis revisions preserve prior versions.
5. Probe information gain is inspectable from raw components.
6. Failed/falsified/partial episodes remain available to cross-episode analysis.
7. One verified episode cannot directly become durable semantic/procedural knowledge.
8. Recurrence alone cannot bypass counterexample/verification governance.
9. Semantic and procedural candidates are separately typed and versioned.
10. Consolidation is reversible/supersedable without rewriting raw episodes.
11. No consolidated procedure automatically gains execution authority.
12. Full unit/compile/CI regression is required before merging v2.

## Non-goals
- foundation-model fine-tuning;
- claiming human-like biological memory;
- automatic destructive forgetting;
- external broker/database dependency in this release;
- autonomous permission escalation;
- treating embeddings/similarity as verification.
