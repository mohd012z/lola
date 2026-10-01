# Lola Agent Episode Engine — Implementation Plan

## Binding specs
- `docs/superpowers/specs/2026-10-02-lola-episode-engine-v2-design.md`
- `docs/superpowers/specs/2026-10-02-lola-agent-episode-engine-design.md`

## Rollback baseline
Green implementation checkpoint: `43c2eb3ed1ba9bf3cfc5048ab2a8c9ce1f98b85e`.
Design-only commits after that checkpoint must not be treated as behavior verification.

## Execution contract
Each release follows RED -> GREEN -> regression. Preserve M0 as source of truth; no agent self-verification; no repetition-based independence inflation.

## AEE-1 — AgentEpisode replay
### Tests first
Create `tests/test_agent_episode.py` covering:
1. DecisionPoint captures known evidence, hypotheses, unknowns, alternatives and selected action.
2. Later result appends actual IG/cost without mutating decision snapshot.
3. Handoff retains inherited evidence ancestry and parent/child agent IDs.
4. Foreign agent/trace events are excluded.
5. `agent.complete` alone cannot yield VERIFIED.
6. Independent verification event can yield VERIFIED when requirements are satisfied.
7. failure -> recovery chain remains ordered/queryable.
8. missing result/verification yields PARTIAL/INCONCLUSIVE rather than invented success.

### Implementation
Create `lola_agent_episode.py` with immutable dataclasses `DecisionPoint`, `DecisionResult`, `Handoff`, `AgentEpisode` and deterministic `build_agent_episode(events, agent_id, trace_id)`.

### Verification
Run targeted tests, full unit suite, compile, then CI. Commit tests before implementation when connector workflow permits separate commits.

## AEE-2 — Repeated Agent Experience
### Tests first
Create `tests/test_repeated_episode.py` covering deterministic context fingerprints; same-origin recurrence separated from independent-origin count; SUCCESS/FAILURE/RECOVERY/STAGNATION/CONDITIONAL/ECHO classifications; counterexamples retained.

### Implementation
Create `lola_repeated_episode.py` with context normalization, recurrence clustering, lineage-aware effective independence and pattern records. Thresholds/config policy injectable; no hard-coded epistemic truth threshold.

## AEE-3 — ExperienceCompiler
### Tests first
Cover duplicate/replay collapse, shared-ancestry collapse, deterministic outputs, raw metric preservation, counterexample extraction, transfer links and no direct memory promotion.

### Implementation
Create `lola_experience_compiler.py`. Input is M1/A1 episodes plus lineage metadata; output is structured pattern/candidate evidence only.

## AEE-4 — AX / AR1 / AP1
### Tests first
Cover contextual capability components, no universal self-rating, routing fallback/stop conditions, anti-pattern recovery evidence, supersession/versioning and advisory-only authority.

### Implementation
Create `lola_agent_routing.py` and candidate schemas. Kernel policy consumes AR1 but action authorization remains separate.

## AEE-5 — Consolidation integration
### Tests first
Cover M2/M3/AR1/AP1 promotion gates, provenance/independence/counterexample/applicability requirements, replay, supersession and retrieval lineage expansion.

### Implementation
Extend `lola_cognitive_learning.py` conservatively. One successful/repeated episode cannot bypass governance. Derived candidates never rewrite M0/M1/A1.

## Final verification
- JSON/schema validation where applicable.
- `python -m compileall` for changed Python modules.
- full unit suite.
- repository smoke checks.
- CI status and logs inspected.
- compare branch against green baseline for unexpected deletions/API regressions.
- final review of evidence lineage, permission boundary and backward compatibility.

## Completion definition
IMPLEMENTED + TESTED + BEHAVIOR VERIFIED + REGRESSION CHECKED. Green build alone is insufficient; unknowns and unexecuted paths are reported explicitly.
