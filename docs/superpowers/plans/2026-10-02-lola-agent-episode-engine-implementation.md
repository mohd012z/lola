# Lola Agent Episode Engine — Execution Ledger

Binding specs: `2026-10-02-lola-episode-engine-v2-design.md` + `2026-10-02-lola-agent-episode-engine-design.md`.

Green rollback baseline: `43c2eb3ed1ba9bf3cfc5048ab2a8c9ce1f98b85e`.

## Invariants
M0 source of truth; no agent self-verification; no repetition-based independence inflation; no candidate execution authority; counterexamples preserved.

## Implemented, awaiting CI
AEE-1 AgentEpisode; AEE-2 repeated-agent patterns; AEE-3 ExperienceCompiler; AEE-4 contextual AX/AR1/AP1 primitives; AEE-5 agent consolidation governance; EpisodeOrchestrator; typed EpisodeJoiner.

## Falsification/regression additions
- STAGNATION_PATTERN explicit regression.
- Parent-emitted handoff must be visible to child while unrelated parent failures remain outside child episode. Initial implementation violated child visibility; fixed in `lola_agent_episode.py`.
- Governance recurrence and independence are orthogonal: one episode with two origins is still insufficient recurrence.

## Deferred until green
Deeper lineage DAG traversal, transfer metrics, aggregate AX builder, and modification of legacy `lola_cognitive_learning.py`.

## Verification gate
Compile + full unit suite + smoke + CI logs + baseline diff. Do not claim behavior complete before these execute green.
