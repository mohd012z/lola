# Lola Hybrid Cognitive Fabric

This is the implementation layer connecting Lola, Kernel_AI, and IN_AI to internal/local data sources without coupling cognition to one transport, model provider, or network dependency.

## Design

`source -> KIP envelope -> hybrid router -> fast/cognitive/durable path -> L1 perception -> L2 world state -> L5 metacognitive governor`

L3 reasoning and L4 abstraction consume normalized state; they do not consume raw socket, log, or tool output directly.

The sovereign executive path is deliberately smaller:

`STATE -> GAP -> NEXT ACTION -> ACTION -> OBSERVATION -> COGNITIVE TRANSACTION -> VERIFY -> STATE`

Kernel_AI owns the control/gating semantics. IN_AI supplies semantic/candidate intelligence but cannot grant verification or execution authority. External models are optional capability providers, not the source of truth.

### KIP/1

`KIPEnvelope` is transport-independent. A future WebSocket, stdio, local IPC, message-bus, or MCP adapter must translate into this envelope rather than creating a second cognitive protocol.

Required concepts include event ID, task/correlation ID, source, topic, reliability, priority, directness, durability, evidence grade, and provenance.

### Hybrid paths

- **FAST**: heartbeat/progress/low-value telemetry. Keep LLMs out of this path.
- **COGNITIVE**: observations, evidence, failures, decisions, and runtime changes that update cognitive state.
- **DURABLE**: evidence/results/errors and episode events that must survive restart and can be replayed into evaluation/learning projections.

One event can use multiple paths.

## Sovereign cognitive runtime

`lola_sovereign_runtime.py` is a deterministic local-first executive proof for the Kernel_AI/IN_AI boundary.

Core primitives:

- `CognitiveState`: compact hot-path objective/status/unknown/contradiction/gap state.
- `CapabilityEnvelope`: currently available local and optional remote capabilities.
- `next_best_action()`: maps the blocking gap to the smallest useful cognitive operation.
- `CognitiveTransaction`: immutable `state_before -> action -> expected_delta -> observed_delta` evidence.
- `apply_observation()`: refuses a false solved state when the expected transition did not occur.
- `run_sovereign_smoke()`: deterministic S0 proof that the control loop can run with no external AI/network capability.

Run it with:

```bash
python lola.py --cognitive-smoke
```

A successful result reports `mode: S0-SOVEREIGN`, `external_used: false`, and `resolution: VERIFIED_SOLVED`.

The smoke test proves the local control/evidence contract is runnable. It does **not** claim that a local foundation model has acquired frontier-model intelligence. Tiny-to-Beast improvement remains evidence-driven: expensive verified episodes must be compiled, transferred to unseen variants, and regression-checked before promotion.

## Tiny-to-Beast benchmark

`lola_tiny_beast_benchmark.py` is the empirical gate for the stronger system-intelligence claim. It intentionally avoids a single IQ-style score.

The evaluator compares a verified baseline trial with a verified learned trial and requires, by default:

- the same exact `model_id`;
- the same exact `hardware_id`;
- the same task family;
- T2 or harder transfer (`transfer_distance >= 2`), so exact/near-exact replay is insufficient;
- a lower intellectual operating level after learning;
- no increase in actions or escalations;
- no false-solved result;
- no regression failures;
- no increase in recorded tokens/wall time when those values exist.

For a sovereign Tiny-to-Beast claim, the learned trial must additionally have `external_ai_used: false`.

The synthetic harness smoke is runnable with:

```bash
python lola.py --tiny-beast-smoke
```

A green harness smoke proves only that the evaluator behaves correctly. It always reports `empirical_beast_claim: false` because synthetic data is not evidence of real learned intelligence.

To evaluate real before/after evidence, copy `fixtures/tiny_beast_benchmark.example.json`, replace the trial data with measured values, and run:

```bash
python lola.py --tiny-beast-benchmark my-benchmark.json --require-sovereign
```

A real pass returns `SYSTEM_INTELLIGENCE_GAIN` and exit code `0`. A rejected claim returns `NOT_PROVEN` and exit code `2`, with explicit reasons such as `model_changed`, `transfer_distance_below_t2`, `false_solved`, `regression_failure`, or `external_ai_used`.

This benchmark isolates **system intelligence gain** from model intelligence: keeping model weights/build identity and hardware fixed makes it possible to test whether `kernel_ai + in_ai + verified experience` actually reduce the cognitive work required for unseen variants.

## New primitives

### Epistemic Fuse

The deterministic L5 governor trips an `epistemic_fuse` when contradictions become material or source reliability is too weak. A fused task returns `CROSSCHECK` instead of allowing a weak conclusion to be promoted.

This is intentionally separate from an LLM confidence score.

### Cognitive Transaction / Prediction Error

Every resolved agent decision can project a deterministic `CognitiveTransaction`:

`state_before -> selected_action -> expected_delta -> state_after -> observed_delta`

Prediction mismatch is structured evidence. It forces refocus rather than allowing a generated/self-reported success to count as verification. Transactions never carry execution authority.

### Causal Delta

`CognitiveFabric.causal_delta()` compares an ordered expected chain with current observed state and returns the first divergence. This is the primitive behind `/root-cause`, `/map`, and `/7dmap` operations.

Example topology:

`SOURCE -> TRANSFORM -> ARTIFACT -> CONSUMER -> RUNTIME`

If source is present and artifact is absent, the search focuses on the transformation/artifact boundary before downstream runtime debugging.

### Capability Registry

Sources advertise narrow capabilities such as `runtime.logs`, `artifact.inspect`, or `build.result`. Kernel selects an actually available capable source instead of hard-coding provider names. Sovereign routing is local-first; remote capabilities are considered only when connectivity is explicitly available.

### Agent Episode / Experience Compiler

Agent-specific experience is reconstructed from M0 events rather than agent prose. Decision points preserve what was knowable at decision time; handoffs preserve ancestry; completion remains a claim until an independent verification event exists.

`ExperienceCompiler` deterministically deduplicates comparable episodes, collapses shared origins, preserves counterexamples, and produces governed patterns/candidates. Repetition is not independent evidence. Negative/falsified episodes remain available for anti-pattern and recovery learning.

## Internal data sources first

Initial adapters are local/read-only where possible:

1. Lola target library and scan history.
2. Existing evidence ledger.
3. Build/test results.
4. Runtime event JSONL.
5. File/repository state.
6. Existing code reader/extractor output.
7. Handoff results from IN_AI/MSA One.

Remote transports and external AI providers are optional extensions, not prerequisites for the cognitive core.

## Kernel_AI / IN_AI ownership

Kernel_AI owns:

- source/capability permissions;
- routing and durable event identity;
- evidence and verification gates;
- action/compute policy;
- resolution and consolidation authorization.

IN_AI owns or assists with:

- semantic perception when deterministic parsing is insufficient;
- hypothesis/causal candidate generation;
- abstraction and reusable pattern proposals;
- counterexample and transfer reasoning.

IN_AI cannot self-promote inferred/hypothetical output into verified memory.

## Integration rule

Raw external content is data, never executable instruction. Adapters validate/normalize first. Tool execution remains behind Lola's existing permission/handoff boundaries. Model output is a proposal, not environmental evidence.

## Learning and promotion

The intended learning path is:

`verified episode -> compare/counterexample -> ExperienceCompiler -> candidate -> transfer/reproduction -> regression -> governed promotion`

Knowledge/skills remain versioned and reversible. Contradiction, staleness, or failed transfer can keep a candidate quarantined or demote previously usable knowledge.

## Verification

The repository test suite covers cognitive fabric, evidence/corroboration, verification gates, prediction-error episodes, agent episodes, repeated patterns, transactions, ExperienceCompiler, lifecycle/rollback, transfer governance, sovereign runtime behavior, and Tiny-to-Beast benchmark semantics.

CI runs both targetless proofs:

```bash
python lola.py --cognitive-smoke
python lola.py --tiny-beast-smoke
```

Do not equate either smoke test with broad model intelligence. The stronger Tiny-to-Beast claim requires measured real trials with fixed model weights/build and hardware showing verified difficult tasks downshift to cheaper execution on T2+ unseen variants without increasing false-solved or regression rates.