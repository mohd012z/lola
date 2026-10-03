# New-LOLA runtime loop v1 — design (frozen)

Date: 2026-10-03. Source: the "Fast Cognitive Mesh" + command-answers in
the shared New LOLA thread ("New LOLA runtime identity" loop).
Companion to #44 (discovery/learning stage) and #45 (mesh controls).
This PR is the **pipeline that wires the stages together**.

## Base
Built on `feat/cognitive-mesh-controls-v1` (PR #45). Stacking is
intentional: #42 → #43 → #44 → #45 → #46. Merge in order.

## Runtime identity loop (encoded, in order)
UNDERSTAND → MAP → INVENTORY → GAP → THINK → INVENT → PREDICT →
FALSIFY → TEST → OBSERVE → RESEARCH IF NEEDED → CHALLENGE → VERIFY →
SYNTHESIZE → ADAPT STYLE → ANSWER → RECHECK → LEARN

v1 encodes each stage as a deterministic decision point; real agent
execution is the caller's job (planner only decides order/content).

## Module H — `lola_fast_triage.py`
`fast_triage(question, *, verified_state, inspectable) -> Triage`
Cheap path FIRST, in order:
1. ANSWER_FROM_VERIFIED — the question's answer is in `verified_state`
   (token overlap of answer text with question, >= 2 terms) → 0 extra
   work, external access never considered.
2. DETERMINISTIC_INSPECTION — `inspectable` (file/log/diff/test) can
   close the gap (question hits inspectable keywords: file, log, diff,
   test, build, status, dependency, schema).
3. COMPLEXITY_MAP — otherwise build the radar map and continue.
Triage carries `route` ∈ {ANSWER, INSPECT, MAP}, `why`, and
`external_justified: bool` (False until the research gate says yes).

## Module I — `lola_research_stages.py`
`plan_research(gap, *, frozen_idea, local_inventory, external_hits) ->
ResearchPlan`
Staged, in frozen order: local knowledge → evidence inventory →
KNOWN/UNKNOWN → internal hypotheses → FREEZE → research plan →
source selection.
- **Source hierarchy** (order = trust, not convenience):
  PRIMARY (code/runtime/docs/spec/raw data) → SECONDARY (analysis) →
  COMMUNITY (issues/forums) → AI (any model). AI is last, for
  hypothesis expansion/critique only.
- **AI agreement ≠ evidence**: `ai_agreement` field counts models
  that agreed but contributes ZERO to evidence count.
- **Query tree**: root question + derived sub-queries from gaps found;
  results may spawn children (the plan is a tree, not a keyword pile).
`source_rank(name) -> int`; plans validate every listed source against
its claimed class (mismatch → ValueError).

## Module J — `lola_evidence_bus.py`
`EvidenceBus` — shared state, isolated working context:
- agents register `Finding(finding, evidence_ids, unknowns,
  contradictions, next_gap)` — compressed, no essays;
- `discriminating_evidence(claim_a, claim_b)` → the evidence ids
  present for one claim and not the other; empty → the evidence does
  NOT discriminate (both claims stand unverified — do not pick a
  winner by agent count);
- `verdict(claim_a, claim_b)` → (winner | None, discriminating,
  note). Winner requires: discriminating evidence exists AND one claim
  is CONTRADICTED by bus evidence OR the other is fully supported and
  the other has no support.
- `pollution_guard` — an agent may only cite evidence_ids that exist on
  the bus (unknown id → ValueError).

## Module K — `lola_runtime_loop.py`
`run_loop(question, *, verified_state, inspectable, inventory,
  frozen_idea, external_hits, budget=None) -> LoopReport`
Composes triage → radar → gap → novelty → research gate → evidence
bus → verify → learn:
- STOP conditions from #45 checked after every stage; report carries
  `stopped_by`.
- **Novelty-before-external is enforced in code**: if `frozen_idea`
  exists and `external_hits` are supplied but the freeze timestamp
  order can't be proven (frozen_after_external=True flag), the report
  is marked `VIOLATION_NOVELTY_BEFORE_EXTERNAL` and research results
  are quarantined (presented, never learned).
- **Answer quality ≠ agent count ≠ source count ≠ tokens** — report
  fields: `evidence_ids`, `confidence` (via #45 presentation),
  `agents_used`, `external_sources_used`, each reported separately and
  never aggregated into a quality score.
- `/flow` trace: `report.trace` is a list of (step, status) ready for
  `render_flow`.
`learning_governor(report) -> "PROMOTE" | "REJECT" | "RETAIN"`:
PROMOTE requires verified answer + survived transfer/regression
flags + no quarantine; else RETAIN (answer stands, not yet knowledge);
REJECT on CONTRADICTED final confidence.

## Non-goals
No real agents, no network, no LLM calls. The loop decides WHAT and IN
WHAT ORDER; executing waves/specialists is the caller's job. No new
transport/UI.
