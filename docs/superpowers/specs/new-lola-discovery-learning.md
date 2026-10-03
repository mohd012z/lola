# New-LOLA discovery & learning methods (design, frozen)

Date: 2026-10-03. Source: the shared "New LOLA — Deep-Dive Master Flow"
thread (8 substantive answers) cross-checked against the current `mohd012z/lola`
codebase. This spec freezes THREE deterministic, stdlib-only method modules.
Everything else in that flow already exists (Interaction Gateway — PR #43;
LLM source fabric — PR #43; KIPEnvelope, evidence core, epistemic fuse,
cognitive transaction, experience compiler, knowledge lifecycle).

The governing principle the whole thread converges on:

> LOLA thinks independently first, tests its own ideas, asks external
> intelligence only when justified, verifies everything against evidence,
> and learns only from outcomes that survive falsification and transfer.
> **A successful learning cycle should make the next structurally related
> problem require less external intelligence — not more.**

These three modules are the part of that principle not yet in code.

## Module A — `lola_cognition_ladder.py` (Tiny-to-Beast, operational)

A gap enters a cognition ladder; the kernel asks *"what is the smallest
capability capable of closing this specific gap?"* — never "which model do
we use?".

Levels (LLM cost strictly increasing; L0–L4 make **zero** LLM calls):

| L  | name              | llm      | note |
|----|-------------------|----------|------|
| L0 | deterministic     | none     | pure computation / lookup |
| L1 | verified knowledge| none     | retrieved governed knowledge |
| L2 | verified experience| none    | retrieved verified episode / transfer |
| L3 | internal derivation| none    | logic from known facts, no model |
| L4 | novel synthesis   | none     | Novelty Engine (Module B), still no external model |
| L5 | local model       | local    | tiny/large local |
| L6 | stronger model    | stronger | larger local |
| L7 | external intelligence| external| remote LLM / docs / repos |
| L8 | human             | —        | escalation back to the human |

`smallest_capability(*, gap_type, knowledge_available, experience_available,
derivable, novel_candidate, tiers, network_available, human_required) ->
LadderDecision`:

- Returns the **lowest** level that can close the gap, given what is
  available. L0–L4 are chosen **before** any model level — this is the
  zero-LLM / "cheapest useful cognition first" rule, made mechanical.
- A model level (L5/L6/L7) is only returned when no L0–L4 path closes the
  gap AND the required tier is actually available (remote needs
  `network_available`).
- If nothing available and `human_required` is false → `ESCALATE` (L8) with
  a reason, not a silent failure.
- Fully deterministic; the decision is inspectable (`reason` field).

## Module B — `lola_novelty.py` (Novelty Engine + Idea Genome)

Anam's explicit requirement: *"LOLA must have the capability to create a
new idea — novel — before asking external sources."* This is the
**NO_EXTERNAL_HINT** protected phase: a gap that is not closeable by
L0–L3 runs the novelty engine *before* any external source is consulted.

### Idea Genome (structured, not prose)
`IdeaGenome` — an idea is an **executable hypothesis**:
problem, observations, known_facts, assumptions, primitives, abstraction,
mechanism, causal_chain, predictions, counterpredictions, experiment,
falsification_condition, provenance, novelty_lineage, status.
`build_idea_genome(...)` validates the structure (a genome with no
falsification_condition or no prediction is rejected — untestable ideas
are not stored).

### Three novelty levels (strict, so "novel" is not random text)
`novelty_level(*, primitives_known, cross_domain, new_mechanism,
has_testable_prediction) -> N1|N2|N3|NONE`:
- **N1 COMPOSITIONAL** — known A + known B → unseen combination C.
- **N2 STRUCTURAL** — a pattern from domain A transferred to domain B.
- **N3 MECHANISTIC** — a previously *unstated* causal mechanism with a
  testable prediction. N3 is the important target.
- NONE — no genuine novelty claim allowed.

### Freeze-before-external + independence classification
`freeze(idea)` locks `{idea_id, timestamp, evidence, derivation,
predictions}` **before** any external search (prevents post-hoc
contamination). `classify_independence(frozen, external_matches)` returns
one of KNOWN / INDEPENDENT_REDISCOVERY / NOVEL_COMBINATION /
POSSIBLE_EXTENSION / **NO_MATCH_FOUND** — and the invariant:
**NO_MATCH_FOUND must never be reported as WORLD_FIRST** (absence of
evidence is not evidence of novelty).

### Diverge → converge (don't fall in love with idea #1)
`challenge(ideas, evidence)` scores each candidate on the 8 axes (evidence
coverage, causal consistency, assumption burden, contradictions,
testability, falsifiability, information gain, experiment cost) and returns
verdicts TESTABLE / CONTRADICTED / KNOWN_COUNTEREXAMPLE / INSUFFICIENT.
Selection is by scored merit, never by model confidence or order.

## Module C — `lola_learning_gate.py` (Learning Gate / K0–K8 maturity)

"LOLA should not begin *learning* when an external source gives it
information." Five **non-equivalent** layers, and a 13-stage gate.

### Five non-equivalent layers
`Layer` = DATA / INFORMATION / CANDIDATE / VERIFIED / LEARNED.
`classify_layer(source, *, is_external_model) -> Layer`: external AI output
caps at **CANDIDATE** (the K0/K2 rule) — it can never self-declare
VERIFIED or LEARNED. Internal observation can reach VERIFIED only with
observation-grade evidence (ties to the epistemic fuse).

### K0–K8 maturity (complements, does not replace, the existing
ACTIVE/QUARANTINED/REJECTED *status* — that is operational state, K is
evidence maturity)
K0 RAW → K1 OBSERVED → K2 HYPOTHESIS → K3 CORROBORATED → K4 REPRODUCED →
K5 FALSIFICATION-SURVIVED → K6 TRANSFER-VALIDATED → K7 REGRESSION-CLEARED →
K8 GOVERNED.

### 13-stage pre-learning pipeline (deterministic state machine)
RAW → QUARANTINE → NORMALIZE → CLASSIFY → PROVENANCE → DECOMPOSE →
DEDUPLICATE → CONTRADICTION → EVIDENCE_MAP → REPRODUCE → FALSIFY →
TRANSFER → REGRESSION → (PROMOTE | HOLD | REJECT).
`LearningGate.advance(candidate, stage_results)` walks the machine and
stops at the **first** failing gate; a candidate is promoted (→ K8,
status ACTIVE) only if it survives all of REPRODUCE+FALSIFY+TRANSFER+
REGRESSION. `HOLD` means "insufficient, not yet rejected".

### Two learning disciplines
- **Prediction-before-research**: the gate requires a recorded
  self-inventory + prediction (`record_intent`) *before* external
  research is permitted (goal-directed learning; prevents absorbing
  answers).
- **Knowledge moves backward**: `demote(knowledge_id, *, contradiction)`
  lowers the K-level and routes to QUARANTINE/RETEST — learning is not
  irreversible.

## Deliberately out of scope (this slice)
- Actual LLM calls, network, UI, new stack.
- Rewriting the existing `lola_knowledge_lifecycle` (K-levels are a new
  maturity dimension carried *alongside* its version/state).
- Any randomness in idea generation (the engine is a deterministic
  *structure + scoring* harness; the semantic generation itself is the
  L5+ model's job when a model level is actually selected).

## Verification
- `tests/test_new_lola_methods.py` — RED→GREEN: ladder ordering +
  zero-LLM rule + escalation; genome validation + N-levels +
  freeze/independence + NO_MATCH≠WORLD_FIRST + diverge/converge; 5-layer
  non-equivalence + external cap + 13-stage stop-at-first-fail + prediction
  prerequisite + backward demotion.
- Full unit suite + compile gate via CI (`Lola Bot Health`).
- No new dependencies (stdlib only).
