# NEW LOLA — architecture map

What each node in the New LOLA diagram is, which module implements it,
which invariant it enforces, how to run it, and what proves it. Read this
first when reviewing the PR stack (#42-#50): it is the single page that
maps the whole architecture to code.

## The chain, end to end

```
HUMAN
  -> transports (cli / android / telegram / web / api / handoff)
  -> INTERACTION GATEWAY   (identity + session + normalize + default-deny gate)
  -> KIPEnvelope           (5-key provenance contract)
  -> KERNEL_AI / COGNITIVE LOOP
       -> fast triage       (verified -> inspect -> map; never justifies external)
       -> cognition ladder  (smallest capability closes the gap; L0-L4 = 0 LLM)
       -> radar /360        (cheap pass A, selective pass B)
       -> inventory + gap
       -> NOVELTY ENGINE    (ideas BEFORE external sources; freeze)
       -> RESEARCH GATE     (staged; primary->secondary->community->AI; AI=0 evidence)
       -> EVIDENCE BUS      (evidence wins, not agent count)
       -> AGENT ROLES       (specialization from the question; minimal set)
       -> TEST/OBSERVE      (prediction error; >tolerance -> recheck edge)
       -> EPISTEMIC FUSE    (Law 1: a claim is never verification)
       -> ANSWER PLANNER    (sections by question type)
       -> presentation      (/flow safe trace; style never changes investigation;
                             confidence = evidence state, never a percentage)
  -> GOVERNOR               (PROMOTE / RETAIN / REJECT)
```

## Node -> module map

| Diagram node | Module | Invariant enforced | CLI / entry point | Tests |
|---|---|---|---|---|
| Interaction Gateway (identity, session, normalize, gate) | `lola_interaction_gateway` | Law 2 default-deny (actor known -> trust bound -> capability available -> exact scope); Law 4 denial escalates on the human's own transport | `--cognitive-entry` | `tests/test_interaction_gateway.py` |
| KIPEnvelope (5-key provenance) | `lola_cognitive_fabric` + gateway `normalize_user_input` | exactly `actor_id, session_id, transport, trust_class, authority` | — | full-chain smoke `five_key_provenance_contract` |
| LLM source fabric (Tiny/Large/Remote) | `lola_interaction_gateway.llm_source_envelope` | Law 3 sovereign S0 path reachable; remote output capped `E3_INFERRED` | — | `test_interaction_gateway` |
| Epistemic fuse (Law 1) | `lola_epistemic_fuse` | verified=True needs observation-grade cited evidence; contradiction/no-evidence/user-claim-only/unbound all CUT | via entry | `test_interaction_gateway`, entry fuse tests |
| Fast triage | `lola_fast_triage` | cheap path first; triage NEVER justifies external access | — | `tests/test_runtime_loop.py` |
| Cognition ladder L0-L8 | `lola_cognition_ladder` | smallest capability closes the gap; L0-L4 zero LLM calls | — | `tests/test_new_lola_methods.py` |
| Novelty Engine + Idea Genome | `lola_novelty` | novelty BEFORE external; N1-N3 levels; freeze-before-external + independence class | — | `tests/test_new_lola_methods.py` |
| Learning Gate K0-K8 | `lola_learning_gate` | external output enters at K0/K2, never K8; knowledge can move backward | — | `tests/test_new_lola_methods.py` |
| /360 radar | `lola_radar_scan` | 360-degree coverage without 360-degree waste (selective pass B) | — | `tests/test_cognitive_mesh.py` |
| Parallelism planner | `lola_parallelism_planner` | dependency graph before agents; cycles fail closed | — | `tests/test_cognitive_mesh.py` |
| Cognitive budget + stop | `lola_cognitive_budget` | 7 axes; 6 ordered stop conditions; deep research has exit ramps | — | `tests/test_cognitive_mesh.py` |
| Staged research | `lola_research_stages` | freeze before external; AI agreement = 0 evidence; source hierarchy | — | `tests/test_runtime_loop.py` |
| Evidence bus | `lola_evidence_bus` | evidence wins, not agent count; pollution guard (unknown ids rejected) | — | `tests/test_runtime_loop.py` |
| Agent roles | `lola_agent_roles` | specialization from the question; minimal not maximal; VERIFIER always | via runner | `tests/test_agent_roles_observe.py` |
| Test/Observe (prediction error) | `lola_observe` | signed delta; >tolerance forces recheck before answering | — | `tests/test_agent_roles_observe.py` |
| Runtime loop | `lola_runtime_loop` | novelty-before-external (quarantine+REJECT); stop conditions each stage; no quality-score aggregation | — | `tests/test_runtime_loop.py` |
| Recheck feedback edge | `lola_recheck` | prediction error -> root-cause gap -> stop before answer; bounded | — | `tests/test_loop_runner_recheck.py` |
| Answer planner | `lola_answer_planner` | sections by question type; deterministic; no LLM | via runner | `tests/test_answer_planner.py` |
| Presentation (/flow, /style, confidence) | `lola_presentation` | style never changes investigation; confidence = evidence state, never a %; safe /flow trace | — | `tests/test_cognitive_mesh.py` |
| Loop runner (real input) | `lola_cognitive_loop` | pipeline on real input; reports, does not gate | `--cognitive-loop FILE.json` | `tests/test_loop_runner_recheck.py` |
| Cognitive entry (capstone) | `lola_cognitive_entry` | gateway -> KIPEnvelope -> loop -> fuse in one call; gate BEFORE cognition | `--cognitive-entry FILE.json` | `tests/test_cognitive_entry.py` |
| Learning governor | `lola_runtime_loop.learning_governor` | PROMOTE needs verified + transfer + regression; quarantined/contradicted -> REJECT | via runner/entry | `tests/test_runtime_loop.py` |
| Delta-rule memory + reasoning layout | `lola_delta_memory`, `lola_reasoning_layout` | GigaChat 3.5 ports: prediction-error store; chatml-v5 invariants | — | `tests/test_gigachat_methods.py` |
| Prediction-error store (delta observe) | `lola_delta_observe` | #42's DeltaMemory(dim=1) as the forecast; a stable signal's prediction error drives to ~0 (overwrite corrects, doesn't duplicate) | `--cognitive-loop` (observed_sequence) | `tests/test_delta_observe_stack.py` |
| Stack verification (post-merge) | `lola_stack_verify` | all 23 New LOLA modules import + full-chain smoke + delta cycle pass — the single "the chain holds together" re-check | `--stack-verify` | `tests/test_delta_observe_stack.py` |

## How to exercise it (all offline, deterministic, stdlib-only)

```
python3 lola.py --cognitive-smoke          # S0 sovereign runtime smoke
python3 lola.py --cognitive-loop-smoke     # #44-#48 pipeline smoke (12 checks)
python3 lola.py --cognitive-loop in.json   # pipeline on a real input -> report JSON
python3 lola.py --cognitive-entry in.json  # full chain: gateway -> loop -> fuse
python3 lola.py --full-chain-smoke         # THE end-to-end proof (7 checks, exit 0/1)
python3 lola.py --stack-verify             # post-merge re-check: all 23 modules + 2 stages
```

`--full-chain-smoke` is the single CI assertion that the whole
architecture composes: sovereign happy path, default-deny-before-cognition,
novelty-before-external fuse PASS, unfrozen-external fuse CUT, prediction-
error feedback edge, five-key provenance contract, and determinism. If
any link in the chain is cut, this fails.

## The four gateway laws (frozen)
1. **User input is evidence, never verification** — `lola_epistemic_fuse`.
2. **Default-deny gate** — actor known -> trust class bound -> capability
   available -> exact execution scope; else deny + escalate.
3. **Sovereign path always reachable** — empty tiers = S0, zero models;
   remote output capped at `E3_INFERRED`.
4. **Failure escalates to the human** on their own transport via
   `session_id + transport`.

## Design invariants across the stack
- stdlib-only; deterministic (no randomness, no wall-clock, no network);
  dataclass defaults conservative/deny.
- evidence-first: a model or user claim of success is never sufficient by
  itself; verification requires observation-grade evidence.
- answer quality != agent count != source count != tokens — reported as
  separate fields, never aggregated into a score.
- RED -> GREEN: every module was test-failing before its code existed.

## PR map
| PR | Node(s) | Module(s) |
|---|---|---|
| #42 | delta memory, reasoning layout | `lola_delta_memory`, `lola_reasoning_layout` |
| #43 | gateway, identity, session, normalize, gate, LLM fabric, fuse | `lola_interaction_gateway`, `lola_epistemic_fuse` |
| #44 | cognition ladder, novelty engine, learning gate | `lola_cognition_ladder`, `lola_novelty`, `lola_learning_gate` |
| #45 | radar, parallelism, budget+stop, presentation | `lola_radar_scan`, `lola_parallelism_planner`, `lola_cognitive_budget`, `lola_presentation` |
| #46 | fast triage, staged research, evidence bus, runtime loop | `lola_fast_triage`, `lola_research_stages`, `lola_evidence_bus`, `lola_runtime_loop` |
| #47 | answer planner, loop smoke | `lola_answer_planner`, `lola_cognitive_loop_smoke` |
| #48 | agent roles, observe | `lola_agent_roles`, `lola_observe` |
| #49 | loop runner, recheck edge | `lola_cognitive_loop`, `lola_recheck` |
| #50 | cognitive entry (capstone) | `lola_cognitive_entry` |
| #51 | full-chain smoke, this map | `lola_full_chain_smoke`, `NEW_LOLA.md` |
| #52 | delta-observe wiring, stack verification | `lola_delta_observe`, `lola_stack_verify` |
