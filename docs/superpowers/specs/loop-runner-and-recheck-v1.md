# Cognitive-loop runner + recheck feedback edge — design (frozen)

Date: 2026-10-03. Source: master flow's `PREDICTION ERROR -> ROOT CAUSE
/ NEW GAP` edge (currently `needs_recheck` is a dead report field) and
the standing need to run the #44-#48 pipeline on REAL input, not just
smoke. Companion to #47/#48.

## Base
Built on `feat/agent-roles-observe-v1` (PR #48). Merge order:
#42 → #43 → #44 → #45 → #46 → #47 → #48 → #49.

## Module P — `lola_recheck.py`
`RecheckResult` (frozen): cycles (tuple of per-cycle dicts),
needs_recheck (bool), prediction_error (final float|None),
root_cause_gap (str|None), continued (bool).
`recheck_cycle(expected_values, observed_values, *, tolerance=1.0,
max_cycles=3)`:
- validates equal lengths; each cycle i predicts expected_values[i] and
  observes observed_values[i]; delta = observed - expected.
- a cycle whose |delta| > tolerance closes the feedback edge:
  `root_cause_gap = "prediction error at cycle i (delta d)"`,
  `continued = False` — the loop stops BEFORE answering, returns to
  OBSERVE/TEST (the next expected/observed pair in the list is exactly
  the recheck attempt; callers supply it).
- if every cycle is within tolerance → `needs_recheck = False`,
  `continued = True` (the loop may answer).
- max_cycles caps the attempts (deterministic, no infinite loop).
Deterministic; the function never invents observations.

## Module Q — `lola_cognitive_loop.py`
`run_cognitive_loop(input: Mapping) -> dict` — the pipeline on real input.
Input keys (all optional except `question`): `question` (str),
`verified_state` (obj str→str), `inspectable` (list str), `inventory`
(obj known/unknown lists), `frozen_idea` (obj), `external_hits` (list
str), `prediction` (number), `observed` (number).
Returns a JSON-safe dict:
- `report`: fields from LoopReport (answer_type, planned_sections,
  confidence, evidence_ids, agents_used, external_sources_used,
  quarantined, violations, route, stopped_by, prediction_error,
  needs_recheck) — dataclasses.asdict with trace included.
- `roles`: `derive_roles(question, gap=inventory.unknown)` — the
  workers the question actually spawns.
- `flow`: `render_flow(report.trace, task_id, external_ai_used,
  evidence_count, current_uncertainty)` — the /flow output.
- `governor`: `learning_governor(report)`.
- `recheck`: when `report.needs_recheck`, the `RecheckResult` from a
  single observed delta (one cycle) — the feedback edge named.
`task_id` defaults to "loop".

## CLI
`lola.py --cognitive-loop FILE.json` — loads the input JSON, runs
`run_cognitive_loop`, prints the result JSON, exit 0 (the loop always
produces a report; pass/fail is the report's content, not the exit
code — this is a runner, not a gate). Added to `special_modes`;
requires a file argument (parser.error if missing).

## Non-goals
No real agents/network/LLM; no new transports. The runner decides
WHAT/ORDER and reports; executing the roles is the caller's job.
