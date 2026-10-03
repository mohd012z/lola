# NovelCandidate v1 — study record and implementation (PR #56)

Date: 2026-10-03
Study source: shared thread `6ac0e84e-77fc-83ec-90d6-757d01c5e08d` (the
continuation of the GGUF deep-dive thread `6ac0d1f0`). Snapshot: 344
messages (206 from the earlier part + 138 new), decoded from the React
flight payload, verified re-decode-stable (0 text drift between two
independent fetches).

## What the continuation covers (138 new messages)

1. **Rechecked live `mohd012z/lola` again** — reconfirms "merge, not
   replace": the missing layer is FAST CODE INTELLIGENCE (Identifier / AST /
   CodeGraph / ContextCompiler / ModelGateway) — **already delivered in
   PR #55**, so this section is now satisfied; it additionally proposes
   KIP URI-namespace extensions (`task://`, `symbol://`, `episode://`, …)
   and Causal Delta × CodeGraph wiring (deferred, see below).
2. **No-GGUF capability model** — S1 (deterministic) vs S2 (+HF) vs S3
   (+local GGUF); five intelligence sources (structural / experience /
   symbolic / creator / model). Builds on #55.
3. **GGUF binary forensics** (SmolLM2 135M Q4_K, Q4_K_L vs Q4_K_M, tensor
   map, quantization) — APK-side work, needs real files/devices (deferred).
4. **Source-in-APK knowledge packs** — library code as indexed knowledge
   with API/version identity (deferred; code-intel indexing covers the
   mechanism).
5. **Novel/Episode engine design** — the core of this PR:
   - four-layer separation: NovelEngine (POSSIBLE) / NovelCandidate
     (hypothesis) / EpisodeEngine (OBSERVED) / Episode (history), plus
     Experiment and Skill engines;
   - "imagination and observation must never share the same truth status";
   - immutable candidates + lineage (`tested_by`, `evolved_into`,
     `criticized_by`);
   - five-slot structural fingerprint (RESOURCE/OPERATION/TRIGGER/TARGET/
     SCOPE) for model-free duplicate detection;
   - staged indexing L0 hash → L1 structural → L2 symbol → L3 FTS5 → L4
     graph → L5 embedding → L6 GGUF (expensive AI last);
   - the prescribed **v1 vertical slice** and its acceptance test:
     RUN #1 proposes NC-1 → NC-1 fails → Episode E-1 records why; RUN #2
     same problem → index retrieves E-1 → the NC-1 duplicate is suppressed
     → a different candidate is generated.

## What already exists (cross-checked, not duplicated)

| Thread claim | lola state |
|---|---|
| Persistent incremental CodeGraph + identifiers + FTS5 + ContextCompiler | ✅ PR #55 `lola_code_intel.py` (merged, `eebfb3e`) |
| Idea freezing before external sources, independence classification | ✅ `lola_novelty.py` (freeze_idea, NO_MATCH_FOUND never world-first) |
| Fingerprinted repeated-episode analysis (context_fingerprint) | ✅ `lola_repeated_episode.py` |
| Lineage-aware independence, counterexamples | ✅ `lola_evidence_lineage.py`, `lola_lineage_experience.py` |
| Journaled verified-knowledge commit + rollback | ✅ `lola_verified_knowledge_transaction.py` |
| First-class **NovelCandidate object**: immutable record, 5-slot fingerprint, state machine, operator divergence, persistent store, episode-aware gate | ❌ **absent — built here** |

## What this PR implements (`lola_candidate.py`, ~700 lines, stdlib-only, zero model calls)

- `NovelCandidate` — frozen dataclass; title+mechanism required;
  deterministic `NC-` id; **immutable** (state moves return new objects).
- `structural_fingerprint()` — five canonical slots
  (RESOURCE/OPERATION/TRIGGER/TARGET/SCOPE) with an explicit, reviewable
  synonym vocabulary → wording-invariant `FP-` identity.
- State machine: `IMAGINED → CRITICIZED → TESTED → VERIFIED/FALSIFIED`;
  **VERIFIED is unreachable without an observed episode** (model
  confidence can never become system knowledge).
- `Episode` — frozen OBSERVED record (predicted/observed/delta);
  deterministic `EP-` id.
- `apply_operator()` / `diverge()` — 10 deterministic structural operators
  (LAZY, PREDICT, SHARE, COMPILE, CACHE, PREFETCH, EVICT, INVERT,
  SCOPE_CODEBASE, TARGET_LATENCY); children are new IMAGINED hypotheses
  with lineage to their parent; structurally-duplicate children are dropped.
- `CandidateStore` — rebuildable SQLite (candidates + episodes + lineage;
  `journal_mode=MEMORY`, `synchronous=OFF`; fingerprint-indexed).
- `gate()` — NOVEL / DUPLICATE / KNOWN_FAILURE, reading **observations
  only** (fingerprint match against recorded episodes; prose is never
  compared).
- `record_outcome()` — an observed outcome drives the candidate's state
  (PASS→VERIFIED, FAIL/FALSIFIED→FALSIFIED, INCONCLUSIVE/PARTIAL→TESTED).
- `run_candidate_smoke()` — 16 checks, including the thread's literal
  two-run acceptance test.

Wiring (repo conventions): `lola.py --candidate-smoke`;
`lola_stack_verify._MODULES` (25 modules) + `candidate` stage;
`toolchain-check.yml` paths (push + PR) + compile list + "Novel Candidate
smoke test" CI step; `tests/test_candidate.py` (24 tests).

## Deferred (documented, not started)

- KIP URI-namespace extension (`task://`, `symbol://`, `episode://`, …)
  — touches `lola_interaction_gateway` envelope; needs its own careful
  PR + Fatah review.
- Causal Delta × CodeGraph (`MISSING_MODULE_DEPENDENCY` rule) — bridges
  `lola_causal_delta` to #55's graph; next slice.
- NovelEngine orchestration (GapDetector/ContradictionEngine over
  ProblemGraph), GGUF CreatorAdapter, Critic/Falsification engines,
  EpisodeGraph temporal chains, RegressionIndex, MemoryGovernor — each
  needs real endpoints/devices or a design decision before it can be
  evidence-based.
- Semantic (L5/L6) fingerprint unification — the deterministic 5-slot
  fingerprint catches structural duplicates; the thread's example where
  two differently-slotted phrasings unify is a GGUF-semantic task by
  design (expensive AI last).

## Evidence

- `pytest tests/test_candidate.py` — 24 passed (0.11 s).
- Full suite: 638 passed (614 baseline + 24).
- `python lola.py --candidate-smoke` — 16/16 checks passed.
- `python lola.py --stack-verify` — 25/25 modules, `candidate` stage ok.
- `python -m py_compile lola_candidate.py` — clean.
