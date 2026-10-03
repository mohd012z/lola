# New-LOLA cognitive mesh controls v1 — design (frozen)

Date: 2026-10-03. Source: the two later deep-dives in the shared
"New LOLA" thread (the `/360 /research /agent /style /flow` answer and
the "Fast Cognitive Mesh" answer). Companion to
`new-lola-discovery-learning.md` (PR #44).

This is the *runtime* half of the mesh: PR #44 built the
discovery/learning stage; this PR builds the four controls that keep a
parallel investigation fast, bounded, and honest in presentation.

## Frozen invariants
- stdlib only; deterministic (no randomness, no wall-clock, no network);
  no new deps; dataclass defaults conservative.
- **Style never changes investigation** — transforms act on an already
  verified answer structure; the required sections survive every style.
- **Evidence wins, not agent count** — confidence is computed from
  evidence state, never from how many agents/models agreed, and never
  emitted as a fabricated percentage.
- **Parallelism from dependency structure** — items in one wave run in
  parallel; waves are sequential. Dependency cycles are a hard error
  (fail-closed), never silently linearized.
- **Stop conditions are explicit and ordered** — a run continues only
  while no stop condition fires.
- **Cheap pass first** — `/360` is a two-pass radar: score everything
  cheaply, investigate only the non-GREEN/non-LOW set.
- RED -> GREEN: `tests/test_cognitive_mesh.py` fails before the modules
  exist, passes after.

## Module D — `lola_radar_scan.py`
360-universe as a fixed dimension set with keywords; deterministic
relevance score against question tokens:
- ACTIVE  = shares >= 2 keywords, REVIEW = exactly 1, LOW = 0
- status: GREEN (covered by verified knowledge), CYAN (to investigate),
  YELLOW (uncertain), RED (contradiction/failure), GREY (irrelevant)
- `fast_radar(question, *, known=(), uncertain=(), contradictions=())`
  returns per-dimension (status, relevance).
- `pass_b(radar)` = the dimensions worth investigating:
  CYAN + YELLOW + RED, minus GREEN and LOW.
  "look everywhere cheaply, investigate selectively."

## Module E — `lola_parallelism_planner.py`
`plan_parallelism(nodes, edges) -> ParallelPlan`
- Kahn topological waves; wave i fully precedes wave i+1.
- `is_parallel` = any wave with >= 2 items.
- Cyclic input -> `ValueError` (fail-closed).
- Implements "build the dependency graph before spawning agents":
  A,B -> D -> E is sequential; C,F independent join wave 0.

## Module F — `lola_cognitive_budget.py`
`CognitiveBudget` (depth, agents, tokens, tool_calls, research,
external_access, latency_ms) with `consume()` + `within_budget()`.
`stop_condition(state) -> str | None` — first match in fixed order:
1. ANSWERED_WITH_EVIDENCE
2. UNCERTAINTY_CHANGES_NOTHING
3. LOW_INFORMATION_GAIN
4. BUDGET_REACHED
5. EVIDENCE_UNAVAILABLE
6. HUMAN_DECISION_REQUIRED
None -> continue. Critical for a small local system: deep research
must have exit ramps, not run forever.

## Module G — `lola_presentation.py`
- `STYLE_NAMES` = AUTO, COMPACT, BEGINNER, TECHNICAL, ENGINEER,
  MANAGER, RESEARCH, AUDIT, TUTORIAL, TABLE, DIAGRAM.
- `Answer` = ordered sections `(title, text, required)`.
  `apply_style(answer, style)`:
  - required sections survive EVERY style (titles + order identical);
  - COMPACT drops optional sections and truncates text (marked);
  - BEGINNER prepends a plain-language lead (first sentence of the
    first required section);
  - other styles are identity transforms in v1 (contract in place,
    transforms added later without changing the invariant).
- `confidence_from_evidence(claims)` -> `{"confidence": str,
  "evidence_ids": [...], "provenance": [...]}`:
  - CONTRADICTED if any claim contradicted; SUPPORTED if all claims
    have >=1 evidence and none contradicted; PARTIALLY_SUPPORTED if
    mixed supported/unverified; UNVERIFIED if no evidence anywhere.
  - Never a percentage: output is the evidence-state string only.
- `render_flow(trace)` -> safe operational trace: step markers
  done=in-progress= pending, "External AI: used/not used yet",
  evidence count, current uncertainty. Shows actions/sources/states —
  never raw chain-of-thought.

## Non-goals
No real agents, no network, no LLM calls, no UI, no scheduling
(runtime execution of waves is the caller's job — the planner only
decides the order). No style transforms beyond the frozen v1 set.
