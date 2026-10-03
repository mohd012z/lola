# Answer Planner + runtime-loop CLI smoke — design (frozen)

Date: 2026-10-03. Source: the thread's "Answer Planner" section (not yet
implemented) + "smoke test lola and after improvement" + the need to make
the #44-#46 pipeline actually runnable. Companion to #44/#45/#46.

## Base
Built on `feat/runtime-loop-v1` (PR #46). Merge order becomes
#42 → #43 → #44 → #45 → #46 → #47.

## Gap being closed
The runtime loop records an "Answer" trace step but produces no section
structure, and nothing in the launcher drives the pipeline. The thread
specifies an **Answer Planner**: pick required sections by question type
before writing the answer. And lola's own CLI exposes every other
deterministic capability as a `--*-smoke` flag — the New LOLA pipeline
should too, so it is exercisable offline.

## Module L — `lola_answer_planner.py`
`plan_answer(question) -> AnswerPlan`
Deterministic question-type classification by whole-token keyword hits:
- TROUBLESHOOTING: why, error, fail, failed, freeze, frozen, crash,
  crashs, bug, broken, hang, hung, not, working, issue, problem, cause
- RESEARCH: research, study, survey, compare, compared, evaluate,
  analyze, analyse, investigate, evidence, which, best, options
- IMPLEMENTATION: implement, build, create, add, change, modify, write,
  develop, make, deploy, integrate, refactor
Classification: highest keyword-hit count wins; ties broken by fixed
priority TROUBLESHOOTING > RESEARCH > IMPLEMENTATION; zero hits →
GENERIC. The plan carries `question_type`, `reason` (the winning token
set), and `sections` (ordered, all required=True):
- TROUBLESHOOTING: Finding, Evidence, Root cause, Fix, Verification,
  Unknowns
- RESEARCH: Question, Known evidence, Competing explanations, Findings,
  Limitations, Conclusion
- IMPLEMENTATION: Target, Change, Dependencies, Implementation, Tests,
  Regression, Result
- GENERIC: Summary, Evidence, Reasoning, Result, Unknowns

`planned_sections(questions)` convenience for a batch.
The plan is pure function of the question text — deterministic, no
LLM, so the same question always yields the same section set.

## Loop integration (additive, backward compatible)
`lola_runtime_loop.run_loop` computes `plan_answer(question)` and the
report gains two fields with defaults (so existing tests/replace still
work): `answer_type: str` and `planned_sections: tuple`. The "Answer"
trace step becomes "Answer (<type>)".

## Module M — `lola_cognitive_loop_smoke.py`
`run_cognitive_loop_smoke() -> dict` — end-to-end offline smoke of the
New LOLA pipeline, following `run_sovereign_smoke`/`run_tiny_beast_smoke`
conventions (returns dict with "passed": bool; CI/CLI treat missing/False
as failure). Exercises, all deterministic:
1. triage ANSWER (verified state) and MAP (complex) routes;
2. radar pass_b selects non-GREEN/LOW only;
3. loop with a clean freeze → research allowed, not quarantined;
4. loop with NO freeze + external hits → quarantined,
   NOVELTY_BEFORE_EXTERNAL in violations, governor REJECT;
5. answer planner returns the correct type for one troubleshooting,
   one research, one implementation, one generic question;
6. presentation render_flow emits the /flow trace from the report;
7. governor PROMOTE on a verified report with transfer+regression pass;
8. evidence bus: agent count never votes (self-contradiction decides).
Each check appends to a "checks" list; passed = all checks green.

## CLI
`lola.py --cognitive-loop-smoke` (no target inputs, same guard as
`--cognitive-smoke`), added to the `special_modes` count and dispatched
to `run_cognitive_loop_smoke()`, printing the JSON result and returning
0 on pass / 1 on fail — identical shape to the existing smoke flags.

## Non-goals
No real agents/network/LLM; no change to existing smoke commands; the
planner does not render prose (that is the style/answer stage's job) —
it only decides WHICH sections.
