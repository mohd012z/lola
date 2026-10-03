# Lola Internal Cognitive Learning — Release 3 Design

## Goal
Turn Lola's existing hybrid cognitive fabric into an evidence-driven internal learning loop for Kernel_AI / IN_AI. Internal repository, evidence, build, test, runtime, target-library, and handoff sources are normalized into one transport-independent protocol; hypotheses remain distinct from verified claims; verified episodes can become reusable lessons only after corroboration and validation.

## Design principles
1. Reality before inference: direct observations outrank model interpretation.
2. Provenance is mandatory: every material observation carries source, time, task/trace identity, reliability, and evidence class.
3. SUPPORTED is not VERIFIED: matching a hypothesis prediction is insufficient for permanent knowledge.
4. Independent corroboration matters: repeated reports from the same source are not independent evidence.
5. Learning is gated: only verified outcomes can enter consolidation candidates.
6. Transport independence: internal/direct execution is the initial path; WebSocket, IPC, pub/sub, or MCP-style adapters may be added without changing cognitive semantics.
7. Deterministic-first: parsing, hashing, state comparison, scoring, and validation use deterministic code when practical; IN_AI handles semantic interpretation and novel reasoning.
8. Replayable cognition: state-changing cognitive events must be reconstructable from durable events.

## Cognitive path

```text
INTERNAL REALITY
  Evidence Ledger | Repository/Git | Files | Build | Tests | Runtime
  Target Library | IN_AI Handoff
                         |
                         v
                  SOURCE ADAPTERS
                         |
                         v
                 KIP 1.2 ENVELOPE
                         |
                         v
             VALIDATE + NORMALIZE
                         |
                         v
 L1 PERCEPTION -> L2 WORLD MODEL -> L3 REASONING
                         |                |
                         |                +-> prediction / probe
                         |                         |
                         +<----- observation <----+
                         |
                         v
              L5 META / VERIFICATION
                         |
             +-----------+-----------+
             |                       |
         insufficient              verified
             |                       |
         crosscheck                  v
                              L4 ABSTRACTION
                                     |
                                     v
                             EPISODE / LESSON
                                     |
                                     v
                               CONSOLIDATION
```

## Evidence Gradient

Evidence is classified by epistemic distance from observed reality.

- `E0_DIRECT`: direct artifact, runtime, test, file, or tool observation.
- `E1_DERIVED`: deterministic computation from identified E0/E1 inputs, such as a hash comparison or parsed build status.
- `E2_CORROBORATED`: compatible evidence supported by at least two independent source identities or independent validation channels.
- `E3_INFERRED`: causal/semantic inference supported by evidence but not directly observed.
- `E4_HYPOTHETICAL`: unverified prediction, assumption, candidate explanation, or proposed outcome.

Evidence class is not a replacement for source reliability. A fresh E0 observation from a weak source can still require crosscheck.

## Claim lifecycle

```text
PROPOSED
   |
   v
UNRESOLVED
   |
 evidence matches prediction
   v
SUPPORTED
   |
 independent corroboration + required validator(s)
   v
VERIFIED
   |
 contradictory evidence later
   v
REOPENED

Any material contradiction may also move a candidate to FALSIFIED when its required prediction is incompatible with observed reality.
```

`SUPPORTED` MUST NOT be inserted into `verified_claims`. Verification is a separate operation and gate.

## Source adapter contract

Every internal adapter emits a normalized observation rather than directly mutating reasoning or memory.

Required logical fields:
- source identity
- source type
- capability
- task/trace/span identifiers
- timestamp
- topic
- normalized payload
- evidence gradient class
- reliability
- direct/derived status
- optional content hash / artifact reference

Initial adapters:
1. Evidence ledger adapter.
2. Repository/file-state adapter.
3. Build/test-result adapter.
4. Runtime/log-result adapter.
5. Target-library adapter.
6. IN_AI handoff-result adapter.

Adapters are read/normalization boundaries. They do not receive unrestricted execution authority.

## Corroboration

Corroboration groups evidence by the material claim or world-state key it supports. Two observations count as independent only when their source identities or validation channels are independent under configured policy. Duplicate event IDs, replayed events, or repeated observations from one source do not raise evidence to E2.

A corroboration result records:
- claim/key
- supporting evidence IDs
- independent source IDs
- resulting evidence class
- conflicts
- freshness window

## Hypothesis and verification behavior

A hypothesis contains a statement and one or more testable predictions. `evaluate_hypothesis()` compares predictions with the world model and may return `UNRESOLVED`, `FALSIFIED`, or `SUPPORTED`. It never performs final verification.

A separate verification operation promotes a supported hypothesis only when:
- no required prediction is missing;
- no material conflict remains;
- minimum independent corroboration is met;
- required validator results pass;
- the epistemic fuse is not active for the claim/task.

The operation records the verification evidence rather than relying on an LLM confidence statement.

## Prediction error

Before an information-gain probe or action is executed, the relevant expected result is recorded. When an actual result arrives, the episode records:

```text
prediction -> actual -> match/delta -> hypothesis revision -> validator outcome
```

Prediction error is structured data. It is used for capability evaluation and future curriculum generation; it is not automatically interpreted as model failure because environment changes and bad observations remain possible explanations.

## Episode model

An episode is reconstructed from trace-linked KIP events and contains:
- objective;
- initial relevant world state;
- observations/evidence;
- hypotheses and predictions;
- selected probes/actions;
- actual results;
- prediction errors;
- revisions/falsifications;
- verification results;
- final relevant state;
- unresolved unknowns;
- outcome (`VERIFIED`, `PARTIAL`, `FAILED`, `ABORTED`).

Episode construction must be deterministic from stored events where those events are available.

## Consolidation gate

Only `VERIFIED` episodes may generate consolidation candidates. A candidate lesson contains:
- trigger/context;
- causal or diagnostic pattern;
- supporting episode/evidence IDs;
- applicability constraints;
- counterexamples/conflicts;
- proposed procedure or principle;
- confidence derived from evidence, not model self-rating.

A candidate is not permanent semantic/procedural knowledge until it passes configured reproduction, counterexample, or transfer checks. New contradictory evidence can supersede or reopen a consolidated lesson.

## Kernel_AI and IN_AI ownership

Kernel_AI owns:
- source permissions and adapter registration;
- routing and durable event identity;
- evidence/verification gates;
- compute and action policy;
- metacognitive fuse;
- completion and consolidation authorization.

IN_AI owns or assists with:
- semantic perception where deterministic parsing is insufficient;
- hypothesis generation;
- causal reasoning;
- abstraction and candidate pattern generation;
- counterexample proposals;
- transfer-task reasoning.

IN_AI cannot self-promote its E3/E4 output into verified memory.

## Internal-first hybrid transport

Release 3 uses direct/internal adapters and the existing event store first. KIP remains transport-independent so later sources can use local IPC, WebSocket, pub/sub, or MCP-style transports. Transport state affects freshness/reliability but does not change evidence semantics.

## Failure and safety behavior

- Malformed source data is rejected or quarantined before cognitive ingestion.
- Duplicate event IDs are idempotent.
- Missing provenance prevents verification promotion.
- Contradictory direct evidence activates crosscheck rather than averaging conflicting facts.
- A disconnected/stale source reduces freshness and cannot be treated as live evidence.
- Failed validators keep the claim below VERIFIED.
- Consolidation never consumes PARTIAL/FAILED/ABORTED episodes as positive lessons.

## Release-3 acceptance criteria

1. Existing `SUPPORTED -> verified_claims` behavior is removed.
2. Evidence gradient E0-E4 is represented and serialized.
3. At least one reusable internal source-adapter interface normalizes source records to KIP observations.
4. Corroboration distinguishes independent sources from duplicates/repeats.
5. A separate verification gate promotes only eligible SUPPORTED hypotheses.
6. Prediction-versus-actual deltas are recorded.
7. Trace-linked events can be reconstructed into an episode.
8. Only VERIFIED episodes can become consolidation candidates.
9. Existing Release-1/2 behavior remains regression-tested.
10. The implementation remains standard-library-only unless a later design explicitly approves a dependency.

## Non-goals for Release 3

- Training or fine-tuning a foundation model.
- Automatic permanent-memory mutation without verification.
- NATS or another external broker dependency.
- Arbitrary remote WebSocket access.
- Unrestricted shell/execution adapters.
- Full graph database/vector database deployment.
