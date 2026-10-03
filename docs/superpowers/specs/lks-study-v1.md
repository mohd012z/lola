# LKS — LOLA Knowledge Store v1 — study record and implementation

Date: 2026-10-03
Study source: shared thread `6ac11613-3f84-83ec-8511-1f0b79d231eb`
(parts 1–3 of the GGUF deep-dive, 702 messages), sections:
- "what happen after the data lola became large on disk" (Storage
  Intelligence Layer: four-temperature tiers, content addressing,
  chunk-level dedup, knowledge compaction, retention policies)
- "deep-dive compact knowledge to store in storage" (knowledge atoms,
  evidence separation, `KnowledgePacket`, `DeltaMemory`, semantic dedup,
  repetition-as-counter, exceptions survive compaction, contradictions
  are never averaged away, context is part of knowledge)
- "make it as option … different format with gguf, but lola can read gguf"
  (the `.LKS` container: magic `LOLAKS`, versioned header + section index,
  string dictionary, varints, delta-encoded graph edges, BASE + DELTA
  segments / LSM-style compaction, self-indexing, per-segment checksums,
  export policy, `.lkse` chunked encryption — deferred, needs key
  management)

## What is implemented here (v1 slice, deterministic, stdlib-only)

`lola_lks.py` (~900 lines, zero model calls):

- **`KnowledgeAtom`** — subject/relation/object + context/constraints,
  content-addressed by a *form-canonical* fingerprint
  (case/underscore/whitespace invariance). Paraphrase-level dedup stays in
  `lola_candidate.structural_fingerprint` (merge, not replace).
- **`EvidenceRef`** — evidence is a *reference* (id + content hash + class),
  never raw bytes in the knowledge DB. Classes E0–E6 from the thread.
- **`LKSStore`** — idempotent dedup-aware ingestion: repetition increments
  `occurrences` (counter, never copies); duplicate evidence refs are not
  stacked.
- **Law 1 at the storage boundary** — `record_verification()` /
  `record_falsification()` raise `PermissionError` for E0–E2 evidence;
  only E3_DETERMINISTIC / E4_TEST / E5_RUNTIME / E6_REPEATED may change an
  atom out of CANDIDATE. A model or user statement can never verify
  knowledge, at any layer, including storage.
- **`ConflictSet`** — contradictory claims are stored, UNRESOLVED, with
  their supporting evidence ids; never averaged away.
- **Graph** — atom-to-atom edges stored once (relationships referenced,
  not re-described).
- **`export_allowed()`** — export policy gate: LOCAL_ONLY never crosses
  cloud/export; MODEL_LOCAL stays with a local model; CLOUD_ALLOWED /
  SHAREABLE pass the wider transports.
- **Container** — `LOLAKS` magic; header `major, minor, schema,
  min_reader, version, atom_count` + a 6-entry section index (direct seek,
  no scan); sections: string dictionary (varint lengths, IDs everywhere),
  atoms, evidence registry, conflicts, graph (sorted, zigzag-delta-encoded
  endpoints), delta stub. Every segment carries length + CRC-32.
- **`LKSFile`** — BASE + append-only DELTA segments; `snapshot()` = base
  with deltas applied in order (MVCC-style read view); `compact()` =
  deterministic merge into a fresh base (LSM-style, no giant rewrites).
- **Versioning from day one** — readers reject unknown major versions and
  `min_reader` mismatches; bytes are never silently reinterpreted.
- **`run_lks_smoke()`** — 19 deterministic checks incl. container
  round-trip, CRC corruption detection, and compact equivalence.

## Deliberately NOT in v1 (documented, needs own decision)

- `.lkse` chunked authenticated encryption — needs key management
  (Android Keystore equivalent); format has a slot for it but v1 is
  plaintext (the thread itself says obscurity ≠ security).
- Chunk-level (inside-file) dedup and four-temperature *movement*
  (HOT→WARM→COLD→ARCHIVE) — storage-manager work, not knowledge structure.
- `KnowledgePacket` / `DeltaMemory` as first-class objects — v1's
  BASE+DELTA gives the mechanism; the packet grouping is a query-layer
  concern for when a GGUF context compiler consumes LKS.
- GGUF reader / ModelStore (the thread's §14) — deferred, needs real GGUF
  files (see prior study notes).

## Weakness pass (2026-10-03, "deep-dive any weakness then make it improve and reliable")

Adversarial probe of all six newest modules (LKS, concurrent-learning,
candidate, causal-codegraph, env-fabric, apk-security) + the thread's own
"deep-dive weakness" section (msgs 267–279). Findings:

1. **CONFIRMED GAP — stale evidence / false green** (thread weakness #11:
   "cached test PASS isn't necessarily evidence for the new candidate;
   evidence needs sourceHash/dependencyHash/environmentHash/testHash/
   candidateHash — only reuse when relevant inputs match. Otherwise
   STALE EVIDENCE, not green"). LKS v1 had no input binding: a VERIFIED
   atom stayed green forever even after the source/test it was verified
   against changed. **Fixed**: `EvidenceRef.inputs` (name→content-hash
   binding), `LKSStore.freshness(atom_id, current)` → TRUSTED / STALE /
   UNBOUND / NOT_VERIFIED; bindings persist through the container
   (schema v1.2, minor bump — additive), deltas, and compact().
   Legacy unbound refs report UNBOUND (unverifiable — never falsely
   red, never trusted). Law 1 symmetry: only E3–E6 refs can serve as the
   freshness basis.
2. PROBE false-alarm: `CausalCodeGraph()` without an index raising
   TypeError is by design (it is a view over a `CodeIndex`).
3. PROBE clean: LKS re-add after verify keeps state; bus `created_ns`
   staleness is a scheduler concern (P-queue, not storage — thread §10);
   env-fabric negative budgets rejected; LKS export gate is atom-level by
   design (evidence *content* lives outside, keyed by hash).
4. Still open (design-level, not code): #13 capability-escalation lease
   (AuthorityKernel), #6 self-learning poisoning (gate pipeline already
   requires reproduction across cases; LKS freshness covers storage).
   ~~#10 index staleness end-to-end~~ — **closed in this commit** (see
   'Weakness pass 2' below).

## Weakness pass 2 (2026-10-03, "continue recheck and improve weakness")

#10 was closed end-to-end in this commit:

**Gap (proven first, per FAIL→EVIDENCE):** on main, after any disk mutation
(mutate/add/remove a file) a `CodeIndex` consumer could NOT detect
staleness without calling `index()` — a *write* that re-parses. `graph_version()`
stayed static and `find_by_name` kept returning symbols of **removed**
files: LOLA was silently reasoning from stale structure, exactly the
thread's #10 ('Never trust an index whose source hash doesn't match').

**Fix (read-only, deterministic):**
- `CodeIndex.staleness_report()` → `StalenessReport(is_fresh, changed,
  removed, unindexed, unreadable)` — hashes every file under the root
  (no parsing, **no writes**) and compares with recorded file hashes.
  Unreadable files count as unreadable, not silently fresh (fail-closed).
- `ContextCompiler.compile(..., check_staleness=True)` →
  `CompiledContext.stale` — the context carries the verdict so a caller
  never silently reasons from a stale graph; default path stays cheap
  (probe skipped unless asked). `verified` stays False (Law 1).
- Smoke: +9 checks (14→23). Tests: +9 (`CodeIntelStalenessTests`).

**Proof (synthetic AND real-scale, per 'validate against real artifacts,
not only small fixtures'):** copy of the actual lola repo slice (157 .py
files → 1,095 symbols / 3,000 edges): probe = **0.012 s**; correctly
reported `stale (changed=2, removed=1, unindexed=1)`; context flagged
`stale=True, verified=False`; incremental reindex touched exactly 3 of
157 files and cleared staleness.

## Evidence

- `pytest tests/test_lks.py` — 46 passed (0.11 s) — 33 original + 13 freshness
- `pytest tests/test_code_intel.py` — 22 passed (0.18 s) — 13 original + 9 staleness
- full suite — 723 passed (714 + 9), 3.9 s
- `--lks-smoke` — 25/25 · `--code-intel-smoke` — 23/23 (was 14; +9 staleness checks)
- `--stack-verify` — 28 modules, all stages ok
- real-scale proof: 157-file repo slice, 12 ms probe, 3/157 incremental reindex
- CI: paths ×2, compile list, smoke step
