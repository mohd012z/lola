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
Agent activity is appended as events, never retroactively edited:
- `agent.activation`
- `agent.handoff`
- `agent.decision`
- `agent.decision.result`
- `agent.hypothesis`
- `agent.probe`
- `agent.result`
- `agent.revision`
- `agent.failure`
- `agent.recovery`
- `agent.complete`

Common fields: `agent_id`, `agent_role`, `task_id`, `trace_id`, `span_id`, `parent_span_id`, timestamp and evidence/provenance references where material.

## DecisionPoint
A decision snapshot preserves what was knowable at decision time:
- `decision_id`
- `agent_id`, `agent_role`
- `state_before`
- `known_evidence_ids`
- `active_hypothesis_ids`
- `unknowns_before`
- `alternatives`
- `selected_action`
- `selection_basis`
- `expected_information_gain`
- `expected_cost`

The later `agent.decision.result` appends actual information gain, actual cost, result event/evidence IDs and whether a revision was triggered. The original DecisionPoint is immutable.

## Handoff lineage
Every delegation records parent/child agent, requested capability, objective, constraints, inherited evidence IDs, inherited assumptions and unresolved unknowns. The child response records produced evidence, claims/hypotheses, contradictions and unresolved unknowns.

Invariant: downstream repetition of an inherited claim does not create a new independent origin.

## A1 AgentEpisode
An AgentEpisode is a deterministic projection keyed by agent + trace/phase and references its parent TaskEpisode. It contains objective, input evidence, decisions, hypotheses, probes, handoffs, evidence gained, contradictions, revisions, prediction deltas, information-gain records, failures, recoveries, final result, verification and unresolved unknowns.

Agent completion is a claim, not proof. A1 outcome may be VERIFIED, PARTIAL, FAILED, ABORTED, FALSIFIED, SUPERSEDED, STALE or INCONCLUSIVE.

## Failure and recovery
Failure/recovery chains are first-class:
```text
FAIL -> EVIDENCE -> ROOT-CAUSE HYPOTHESIS -> FIX -> RETRY -> VERIFY
```
Failed, falsified and partial episodes remain available as negative/counterexample evidence.

## RA1 repeated-agent patterns
RA1 groups materially comparable A1 episodes using a context fingerprint such as domain, problem family, failure class, environment, artifact type, constraints and available evidence class.

Pattern classes:
- SUCCESS_PATTERN
- FAILURE_PATTERN
- RECOVERY_PATTERN
- STAGNATION_PATTERN
- CONDITIONAL_PATTERN
- ECHO_PATTERN

Repetition triggers investigation; it is never verification by itself.

## Independence under repetition
Episode count and effective independence are separate metrics. Repeated episodes sharing the same `origin_id`, `artifact_hash`, dependent channel, or inherited evidence ancestry do not add independent corroboration merely because they occurred multiple times or passed through different agents.

## Echo detection
If semantically equivalent claims propagate A -> B -> C while lineage resolves to one origin and no independent observation is added, RA1 emits an ECHO_PATTERN. Echo patterns may inform routing/anti-pattern candidates but cannot strengthen evidence grade.

## Stagnation detection
Local stagnation: repeated/equivalent probes with negligible new evidence/information gain inside one episode.
Systematic stagnation: the same low-information path recurring across comparable episodes.

Track raw components such as novel evidence rate, resolved unknowns, duplicate-probe rate, revision rate, contradiction-resolution rate, cost and latency. Thresholds are configurable policy.

## ExperienceCompiler
The ExperienceCompiler is deterministic preprocessing before IN_AI abstraction:
1. select comparable A1/M1 episodes;
2. normalize context fingerprints;
3. deduplicate replay/duplicate episodes;
4. collapse shared evidence ancestry;
5. compute effective independence domains;
6. extract decisions, sequences, outcomes and recovery chains;
7. calculate inspectable information-gain/cost components;
8. identify repeated success/failure/recovery/stagnation/echo patterns;
9. search counterexamples and transfer cases;
10. emit structured candidates for governed abstraction.

IN_AI reasons over these structured candidates rather than treating raw transcript frequency as truth.

## AX cross-agent experience
AX compares agents/capabilities in context using verified historical components: attempts, verified outcomes, recoveries, falsifications, information gain, evidence quality, duplicate-probe rate, contradictions, cost and latency. Store raw components; do not persist one opaque universal capability score.

## AR1 routing candidate
Contains context/applicability fingerprint, preferred capability/agent sequence, fallback/stop conditions, expected evidence/information gain, supporting and contradicting episodes, effective independence, version/supersession links and governance status.

AR1 is advice to Kernel routing. It is not execution permission.

## AP1 anti-pattern candidate
Captures recurring harmful/ineffective reasoning or workflow behavior: trigger/context, behavior to avoid, observed consequence, supporting failure episodes, successful recoveries, applicability and evidence lineage.

## Multi-agent sequence learning
Sequence frequency alone cannot select a route. Compare sequences using outcome, independent evidence gained, information gain, cost, latency, failures and counterexamples. Search for causal/contextual conditions before proposing AR1.

## Multiple episode engines
Task, Agent, Failure, Tool/Probe, Runtime, Temporal and Reasoning engines are projections over the same M0 events. They reference event IDs rather than copying evidence. An EpisodeOrchestrator dispatches relevant events; an EpisodeJoiner records typed relationships among episode projections.

Suggested relations: PARENT_OF, CHILD_OF, PRECEDES, CAUSES, CORRELATES_WITH, CONTRADICTS, VERIFIES, SUPERSEDES, SAME_TASK, SAME_FAILURE, SAME_AGENT, SAME_ARTIFACT, TRANSFER_OF, COUNTEREXAMPLE_OF.

No naive engine voting is allowed. All apparent agreement is lineage-collapsed before independence is assessed.

## Multi-resolution episodes
Support MICRO (decision/probe), MESO (diagnosis/repair/verification phase), MACRO (complete task), and META (cross-task pattern) views. Higher-resolution summaries retain references to lower-level episodes/events for replay.

## Governance outputs
ExperienceCompiler may propose:
- M2 semantic candidate
- M3 procedural candidate
- AR1 routing candidate
- AP1 anti-pattern candidate

All require provenance, independence, counterexample, applicability and verification governance appropriate to their type. No candidate automatically gains action authority.

## Acceptance criteria
1. Existing R3/v2 tests remain green.
2. DecisionPoint preserves belief/evidence/unknowns at decision time and is never rewritten by later knowledge.
3. Agent handoffs retain evidence ancestry.
4. Agent self-report cannot mark an episode VERIFIED.
5. Repeated same-origin episodes do not inflate independence.
6. Echo propagation across agents is detectable.
7. Failed/falsified/partial episodes participate in counterexample analysis.
8. Repeated failures can produce AP1; verified recoveries can produce recovery patterns.
9. Capability evidence remains contextual and inspectable rather than a universal self-rating.
10. AR1 routing candidates remain advisory and governed.
11. Multiple episode engines share M0 and cannot vote around evidence lineage.
12. ExperienceCompiler output is deterministic for the same event/episode inputs and policy version.
13. All derived objects trace to raw events/evidence.
14. Full compile/unit/CI regression is green before promotion/merge.

## Implementation releases
- AEE-1: agent event contracts, DecisionPoint, handoff lineage, deterministic AgentEpisode replay.
- AEE-2: context fingerprints and RA1 repeated pattern detection.
- AEE-3: ExperienceCompiler, ancestry collapse, independence accounting, counterexamples.
- AEE-4: AX contextual capability evidence, AR1 routing and AP1 anti-pattern candidates.
- AEE-5: connect outputs to consolidation governor, retrieval/replay, regression and CI.
