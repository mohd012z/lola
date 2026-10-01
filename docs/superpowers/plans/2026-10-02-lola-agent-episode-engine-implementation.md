# Lola Agent Episode Engine — Implementation Plan

## Binding specs
- `docs/superpowers/specs/2026-10-02-lola-episode-engine-v2-design.md`
- `docs/superpowers/specs/2026-10-02-lola-agent-episode-engine-design.md`

## Rollback baseline
Green implementation checkpoint: `43c2eb3ed1ba9bf3cfc5048ab2a8c9ce1f98b85e`.
Design-only commits after that checkpoint must not be treated as behavior verification.

## Execution contract
Each release follows RED -> GREEN -> regression. Preserve M0 as source of truth; no agent self-verification; no repetition-based independence inflation.

## Status ledger
- AEE-1 AgentEpisode replay: IMPLEMENTED, CI NOT YET VERIFIED.
- AEE-2 Repeated Agent Experience: IMPLEMENTED, CI NOT YET VERIFIED.
- AEE-3 ExperienceCompiler: IMPLEMENTED minimal deterministic core, deeper ancestry/transfer metrics pending, CI NOT YET VERIFIED.
- AEE-4 AX/AR1/AP1: contextual candidate core IMPLEMENTED; aggregate AX builder pending, CI NOT YET VERIFIED.
- AEE-5 Consolidation: separate agent governance boundary IMPLEMENTED; integration into legacy `lola_cognitive_learning.py` intentionally deferred until regression evidence is green.
- EpisodeOrchestrator + typed EpisodeJoiner: IMPLEMENTED minimal deterministic core, CI NOT YET VERIFIED.

## AEE-1 — AgentEpisode replay
Tests cover DecisionPoint snapshots/results, handoff ancestry, filtering, self-verification rejection, external verification, recovery order and unresolved decisions. Implementation: `lola_agent_episode.py`.

## AEE-2 — Repeated Agent Experience
Tests cover deterministic context fingerprints, same-origin independence collapse, failure/recovery/echo pattern classification. Implementation: `lola_repeated_episode.py`.

## AEE-3 — ExperienceCompiler
Tests cover duplicate episode collapse, shared-origin collapse, deterministic output, counterexample retention and no direct memory promotion. Implementation: `lola_experience_compiler.py`.

## AEE-4 — AX / AR1 / AP1
Tests cover inspectable capability components, advisory routing and recovery-preserving anti-patterns. Implementation: `lola_agent_routing.py`.

## AEE-5 — Consolidation integration
Agent governance tests cover independence, unresolved counterexamples and execution-authority separation. Implementation: `lola_agent_consolidation.py`. Legacy consolidation integration remains gated on green CI to avoid disturbing the verified R3 boundary prematurely.

## Multi-engine core
`lola_episode_orchestrator.py` performs compact deterministic dispatch. `lola_episode_joiner.py` supports typed links and deliberately excludes voting semantics.

## Final verification required before claiming behavior complete
- JSON/schema validation where applicable.
- `python -m compileall` for changed Python modules.
- full unit suite.
- repository smoke checks.
- CI status and logs inspected.
- compare branch against green baseline for unexpected deletions/API regressions.
- final review of evidence lineage, permission boundary and backward compatibility.

## Completion definition
IMPLEMENTED + TESTED + BEHAVIOR VERIFIED + REGRESSION CHECKED. Current new implementation is NOT behavior-verified until CI executes green.
