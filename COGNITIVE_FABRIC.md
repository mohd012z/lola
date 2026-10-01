# Lola Hybrid Cognitive Fabric

This is the first implementation layer for connecting Lola, Kernel_AI, and IN_AI to internal/local data sources without coupling cognition to one transport.

## Design

`source -> KIP envelope -> hybrid router -> fast/cognitive/durable path -> L1 perception -> L2 world state -> L5 metacognitive governor`

L3 reasoning and L4 abstraction consume the normalized state; they should not consume raw socket, log, or tool output directly.

### KIP/1

`KIPEnvelope` is transport-independent. A future WebSocket, stdio, local IPC, message-bus, or MCP adapter must translate into this envelope rather than creating a second cognitive protocol.

Required concepts include event ID, task/correlation ID, source, topic, reliability, priority, directness, and durability.

### Hybrid paths

- **FAST**: heartbeat/progress/low-value telemetry. Keep LLMs out of this path.
- **COGNITIVE**: observations, evidence, failures, and runtime changes that update the cognitive state.
- **DURABLE**: evidence/results/errors that must survive restart and can be replayed into training/evaluation episodes.

One event can use multiple paths.

## New primitives

### Epistemic Fuse

The deterministic L5 governor trips an `epistemic_fuse` when contradictions become material or source reliability is too weak. A fused task returns `CROSSCHECK` instead of allowing a weak conclusion to be promoted.

This is intentionally separate from an LLM confidence score.

### Causal Delta

`CognitiveFabric.causal_delta()` compares an ordered expected chain with current observed state and returns the first divergence. This is the primitive behind future `/root-cause`, `/map`, and `/7dmap` operations.

Example topology:

`SOURCE -> TRANSFORM -> ARTIFACT -> CONSUMER -> RUNTIME`

If source is present and artifact is absent, the search should focus on the transformation/artifact boundary before downstream runtime debugging.

### Capability Registry

Sources advertise narrow capabilities such as `runtime.logs`, `artifact.inspect`, or `build.result`. Kernel selects the most reliable capable source rather than hard-coding source names.

## Internal data sources first

Initial adapters should be local/read-only where possible:

1. Lola target library and scan history.
2. Existing evidence ledger.
3. Build/test results.
4. Runtime event JSONL.
5. File/repository state.
6. Existing code reader/extractor output.
7. Handoff results from IN_AI/MSA One.

Remote transports are optional extensions, not prerequisites.

## Integration rule

Raw external content is data, never executable instruction. Adapters validate/normalize first. Tool execution remains behind Lola's existing permission and handoff boundaries.

## Next implementation slices

1. Add adapters for `lola_evidence.py`, target library, build/test output, and runtime JSONL.
2. Add KIP stdio/local-IPC transport; WebSocket remains optional for live remote/mobile sources.
3. Add OpenTelemetry-compatible trace/correlation IDs for observation -> decision -> action -> result chains.
4. Feed compact evidence packs into IN_AI L3 rather than complete raw logs.
5. Add L3 hypotheses/predictions/information-gain planning.
6. Add L4 episode -> pattern -> counterexample -> transfer -> consolidation pipeline.
7. Promote only verified/generalized lessons into durable memory.

## Verification

`tests/test_cognitive_fabric.py` covers hybrid routing, event idempotency, durable replay, contradiction fuse behavior, first-divergence localization, and capability-source selection.
