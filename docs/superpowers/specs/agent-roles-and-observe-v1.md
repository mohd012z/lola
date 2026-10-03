# Agent roles + observe stage — design (frozen)

Date: 2026-10-03. Source: the thread's "Give agents different cognitive
roles" / "specialization should emerge from the question" sections and
the master flow's TEST → OBSERVE → PREDICTION ERROR → ROOT CAUSE / NEW
GAP stage. Companion to #46 (runtime loop).

## Base
Built on `feat/answer-planner-loop-smoke` (PR #47). Merge order:
#42 → #43 → #44 → #45 → #46 → #47 → #48.

NOTE: #42's `lola_delta_memory.DeltaMemory` (prediction-error store) is
NOT on this branch's base (#42 unmerged). `lola_observe` therefore
computes the prediction delta self-contained; the concept matches
DeltaMemory by construction, and wiring its per-step store in after
#42 merges is a follow-up, not a dependency here.

## Module N — `lola_agent_roles.py`
Seven cognitive roles (the thread's set), fixed lifecycle order:
EXPLORER → ANALYST → RESEARCHER → SKEPTIC → EXPERIMENTER → VERIFIER →
SYNTHESIZER.
- `role_for_question_type(t)` — the canned template per question type
  (all end in VERIFIER + SYNTHESIZER).
- `derive_roles(question, gap=())` — **specialization emerges from the
  question**: EXPLORER (map first) + VERIFIER (always — evidence
  philosophy) + type-specific roles; SYNTHESIZER only when there is
  genuinely more than one stream to integrate (>= 2 open gaps, or a
  RESEARCH question with any gap). Minimal, not maximal: a known fact
  gets no SYNTHESIZER.
- Deterministic; returned in LIFECYCLE order.
- Roles decide WHICH workers exist; the kernel does not run a
  permanent pool.

## Module O — `lola_observe.py`
TEST → OBSERVE → PREDICTION ERROR:
- `Observation` (frozen): observation_id, expected, observed,
  prediction_error (= observed − expected, signed delta), source,
  needs_recheck.
- `predict(v)` identity hook; `compute_prediction_error(e, o)`;
  `record_observation(id, *, expected, observed, source="",
  tolerance=1.0)`.
- `needs_recheck = abs(prediction_error) > tolerance`: a small drift
  within tolerance is fine (answer stands); a large delta forces a
  RECHECK before answering — the prediction-error loop from the master
  flow. Tolerance default 1.0, explicit parameter.

## Loop integration (additive)
`run_loop(..., prediction=None, observed=None)`: when BOTH are given,
the OBSERVE stage computes the delta (trace step "Observe"); the report
gains `prediction_error: float | None` and `needs_recheck: bool`
(defaults keep all #47/#46 tests passing).

## Non-goals
No real agents/processes, no network, no LLM. No wiring to DeltaMemory
(unmerged #42) — concept-compatible only.
