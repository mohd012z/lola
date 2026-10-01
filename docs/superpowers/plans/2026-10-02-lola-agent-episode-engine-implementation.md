# Lola Agent Episode Engine — Implementation Plan / Ledger

## Binding specs
- `docs/superpowers/specs/2026-10-02-lola-episode-engine-v2-design.md`
- `docs/superpowers/specs/2026-10-02-lola-agent-episode-engine-design.md`

## Rollback baseline
Green R3 checkpoint: `43c2eb3ed1ba9bf3cfc5048ab2a8c9ce1f98b85e`. Later design commits are not behavior verification.

## Invariants
M0 remains source of truth. Agent self-report cannot verify itself. Repetition cannot inflate independence. Derived candidates have no execution authority. Counterexamples remain visible.

## Implemented batches (pending CI verification)
- AEE-1 `lola_agent_episode.py`: DecisionPoint/result separation, handoff ancestry, filtering, external verification, failure/recovery, unresolved decision handling.
- AEE-2 `lola_repeated_episode.py`: deterministic fingerprints; SUCCESS/FAILURE/RECOVERY/STAGNATION/CONDITIONAL/ECHO pattern analysis; effective origin counting.
- AEE-3 `lola_experience_compiler.py`: duplicate collapse, shared-origin collapse, deterministic pattern compilation, counterexample retention, no direct promotion.
- AEE-4 `lola_agent_routing.py`: contextual capability components, AR1 advisory routing, AP1 anti-pattern candidates.
- AEE-5 `lola_agent_consolidation.py`: independent-origin, recurrence, applicability and counterexample governance with explicit no-authority result.
- Multi-engine: `lola_episode_orchestrator.py` + `lola_episode_joiner.py` compact deterministic projection dispatch and typed episode links.

## Rulings
- Keep agent consolidation in a separate boundary until CI is green; modifying legacy `lola_cognitive_learning.py` before regression evidence would unnecessarily risk the verified R3 contract.
- Treat a governance pass as candidate eligibility, never as memory truth or execution permission.
- Keep context fingerprint deterministic and order-insensitive for collection-valued context fields.
- Stagnation classification is explicit when any comparable episode is marked stagnated unless the whole cluster is a stronger echo/recovery/failure/success class.

## Required verification before completion claim
1. compile changed Python modules;
2. run full unit suite including new agent/repeated/compiler/routing/governance/orchestrator/joiner tests;
3. repository smoke checks;
4. inspect CI jobs/logs;
5. compare against green baseline for unexpected API deletion/regression;
6. only then integrate deeper ancestry DAG/transfer metrics or legacy consolidation.

## Completion definition
IMPLEMENTED + TESTED + BEHAVIOR VERIFIED + REGRESSION CHECKED. Current code is implemented with test contracts but remains UNVERIFIED until CI executes.
