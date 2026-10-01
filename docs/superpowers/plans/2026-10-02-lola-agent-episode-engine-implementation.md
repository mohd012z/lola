# Lola Agent Episode Engine — Implementation Plan / Ledger

## Binding specs
`docs/superpowers/specs/2026-10-02-lola-episode-engine-v2-design.md` and `docs/superpowers/specs/2026-10-02-lola-agent-episode-engine-design.md`.

## Rollback baseline
Green R3 checkpoint: `43c2eb3ed1ba9bf3cfc5048ab2a8c9ce1f98b85e`. Later design commits are not behavior verification.

## Invariants
M0 is source of truth; agent self-report cannot verify itself; repetition cannot inflate independence; derived candidates have no execution authority; counterexamples remain visible.

## Implemented batches — pending CI
- AEE-1 `lola_agent_episode.py`: immutable DecisionPoint/result split, parent/child handoff ancestry, agent/trace isolation, external verification, failure/recovery, unresolved decisions.
- AEE-2 `lola_repeated_episode.py`: deterministic fingerprints; SUCCESS/FAILURE/RECOVERY/STAGNATION/CONDITIONAL/ECHO; effective origin counting.
- AEE-3 `lola_experience_compiler.py`: duplicate/shared-origin collapse, deterministic compilation, counterexamples, no promotion.
- AEE-4 `lola_agent_routing.py`: contextual capability components, AR1 advisory routing, AP1 anti-patterns.
- AEE-5 `lola_agent_consolidation.py`: applicability/independence/recurrence/counterexample governance; no authority.
- Multi-engine: `lola_episode_orchestrator.py` and `lola_episode_joiner.py`.

## Rulings / falsification findings
- Legacy consolidation integration deferred until green CI to protect verified R3 boundary.
- Governance pass means candidate eligibility only.
- Context fingerprint is deterministic and collection-order insensitive.
- Added explicit STAGNATION_PATTERN regression.
- Falsification found a handoff-lineage visibility defect: a handoff emitted by parent `kernel` was initially invisible to child `build`. Fixed by including parent/child identities in event selection while keeping non-handoff parent failures isolated from the child episode.

## Required verification
Compile changed Python; full unit suite; smoke checks; inspect CI logs; compare against green baseline for API/deletion regressions. Only then proceed to deeper lineage DAG/transfer metrics or legacy consolidation integration.

## Completion definition
IMPLEMENTED + TESTED + BEHAVIOR VERIFIED + REGRESSION CHECKED. Current code is implemented with tests but remains UNVERIFIED until CI executes.
