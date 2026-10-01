# Lola Agent + Repeated-Agent Episode Engine — Design Extension

## Goal
Extend Episode Engine v2 with agent-specific experience while preserving M0 as the single source of truth. Agent projections may learn routing, recovery, failure and collaboration patterns, but may not manufacture evidence, self-verify, or grant execution authority.

## Memory planes
```text
M0   immutable KIP/raw events
M1   task episodes
A1   agent episodes
RA1  repeated-agent pattern sets
AX   cross-agent experience
M1X  cross-task/counterexample/transfer sets
M2   semantic candidates
M3   procedural candidates
AR1  routing-policy candidates
AP1  anti-pattern candidates
```
All planes above M0 are derived and replayable.

## Agent event contracts
Agent activity is appended as events, never retroactively edited: `agent.activation`, `agent.handoff`, `agent.decision`, `agent.decision.result`, `agent.hypothesis`, `agent.probe`, `agent.result`, `agent.revision`, `agent.failure`, `agent.recovery`, `agent.complete`.

Common fields: `agent_id`, `agent_role`, `task_id`, `trace_id`, `span_id`, `parent_span_id`, timestamp and evidence/provenance references where material.

## DecisionPoint
A decision snapshot preserves what was knowable at decision time: decision/agent identity, state before, known evidence, active hypotheses, unknowns, alternatives, selected action/basis, expected information gain and cost. A later result event appends actual IG/cost, result references and revision status. The original DecisionPoint is immutable.

## Handoff lineage
Every delegation records parent/child agent, requested capability, objective, constraints, inherited evidence, inherited assumptions and unresolved unknowns. Downstream repetition of inherited claims does not create independent origins.

## A1 AgentEpisode
A deterministic projection keyed by agent + trace/phase, referencing its parent TaskEpisode. Agent completion is a claim, not proof. Outcomes may include VERIFIED, PARTIAL, FAILED, ABORTED, FALSIFIED, SUPERSEDED, STALE or INCONCLUSIVE.

## Failure and recovery
```text
FAIL -> EVIDENCE -> ROOT-CAUSE HYPOTHESIS -> FIX -> RETRY -> VERIFY
```
Failed/falsified/partial episodes remain counterexample evidence.

## RA1 repeated-agent patterns
Group materially comparable A1 episodes using deterministic context fingerprints. Pattern classes: SUCCESS_PATTERN, FAILURE_PATTERN, RECOVERY_PATTERN, STAGNATION_PATTERN, CONDITIONAL_PATTERN, ECHO_PATTERN. Repetition triggers investigation; never verification by itself.

## Independence under repetition
Episode count and effective independence are separate. Shared `origin_id`, `artifact_hash`, dependent channel, or inherited ancestry cannot add independent corroboration merely through repetition or different agents.

## ExperienceCompiler
Deterministically select comparable episodes, normalize contexts, deduplicate, collapse shared ancestry, compute independence, extract decisions/sequences/outcomes/recovery, preserve raw metrics, find repeated patterns/counterexamples/transfer, and emit structured governed candidates. IN_AI consumes these structures rather than transcript frequency as truth.

## AX / AR1 / AP1
AX stores contextual capability evidence components rather than one universal score. AR1 stores advisory routing candidates with applicability, preferred/fallback sequences, evidence, counterexamples and versioning. AP1 stores recurring ineffective/harmful behaviors and verified recoveries. None grant execution authority.

## Multiple episode engines
Task, Agent, Failure, Tool/Probe, Runtime, Temporal and Reasoning engines are projections over M0. EpisodeOrchestrator dispatches relevant events. EpisodeJoiner records typed relationships: PARENT_OF, CHILD_OF, PRECEDES, CAUSES, CORRELATES_WITH, CONTRADICTS, VERIFIES, SUPERSEDES, SAME_TASK, SAME_FAILURE, SAME_AGENT, SAME_ARTIFACT, TRANSFER_OF, COUNTEREXAMPLE_OF. No naive engine voting; agreement is lineage-collapsed first.

## Multi-resolution episodes
MICRO decision/probe, MESO diagnostic/repair/verification phase, MACRO complete task, META cross-task pattern. Higher levels retain lower-level references for replay.

## Governance
ExperienceCompiler may propose M2, M3, AR1 and AP1. Promotion requires type-appropriate provenance, effective independence, recurrence, counterexample resolution, applicability and verification. A governance pass still does not confer action authority.

## Acceptance criteria
1. Existing R3/v2 tests remain green.
2. DecisionPoint preserves knowledge at decision time.
3. Handoffs retain evidence ancestry.
4. Agent self-report cannot verify an episode.
5. Same-origin repetition cannot inflate independence.
6. Echo propagation is detectable.
7. Negative episodes participate in counterexample analysis.
8. Repeated failures/recoveries can generate AP1/recovery evidence.
9. Capability evidence is contextual and inspectable.
10. AR1 remains advisory.
11. Multiple engines share M0 and cannot vote around lineage.
12. ExperienceCompiler is deterministic for identical inputs/policy.
13. Derived objects trace to raw evidence.
14. Full compile/unit/CI regression must be green before merge.

## Implementation releases
AEE-1 AgentEpisode; AEE-2 repeated patterns; AEE-3 ExperienceCompiler; AEE-4 AX/AR1/AP1; AEE-5 consolidation/retrieval/regression.
