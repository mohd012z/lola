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

## Evidence

- `pytest tests/test_lks.py` — 33 passed (0.11 s)
- full suite — 701 passed (668 baseline + 33)
- `--lks-smoke` — 19/19
- stack-verify — 28 modules + lks stage
- CI: paths ×2, compile list, smoke step
