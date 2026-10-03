# Code Intelligence layer — study → implementation record

**Source:** shared ChatGPT thread `6ac0d1f0-4c40-83ec-83d3-fd41236eadeb`
("List GGUF Sources and Recommendations", 206 messages, decoded
`/opt/data/cache/scratch/share3/`). Studied 2026-10-03.

## What the thread actually said (distilled)

The thread starts as a GGUF model-sourcing survey (Hugging Face / ggml-org /
Bartowski / Unsloth; Qwen3 0.6B–4B, Qwen3.5, Gemma, Qwen2.5-Coder-1.5B) but its
**final two sections re-inspected the real `mohd012z/lola` repository** and
changed the conclusion:

> "I would not redesign `kernel_ai`, `in_ai`, `CognitiveTransaction`, Causal
> Delta, ExperienceCompiler, or the FAST/COGNITIVE/DURABLE fabric. Those are
> already LOLA's strongest differentiators. **Build the new high-speed
> CodeGraph/Identifier/Context/GGUF layer underneath them.**"

Its own gap map, cross-checked against main (2026-10-03):

| Thread claim | Reality on main | Verdict |
|---|---|---|
| Creator/imagination missing | `lola_novelty` (Idea Genome, freeze-before-external) | already exists — thread stale |
| Model ladder missing | `lola_cognition_ladder` (S0 sovereign, remote capped E3) | already exists — thread stale |
| Agent roles missing | `lola_agent_roles`, `lola_agent_routing` | already exists — thread stale |
| Remote-model communication missing | `lola_interaction_gateway.llm_source_envelope` | already exists — thread stale |
| Retrieval missing | `lola_memory_retrieval` (memory, not code) | exists for memory only |
| **Identifier Engine + Incremental CodeIndex** | `lola_code_inspector.py` = one-shot, Python-only, no IDs, no persistence | **GAP (thread P0)** |
| **SQLite CodeGraph + FTS5** | `llm_security/codegraph.py` = guardrail eval only, not the codebase | **GAP (thread P1)** |
| **ContextCompiler (target+callers+callees+tests)** | absent | **GAP (thread P2)** |
| HF/LAN/local ModelGateway adapters, FIM, KV cache, runtime profiler | absent | deferred (need real endpoints/devices) |

## What was implemented (this PR)

`lola_code_intel.py` — stdlib-only (`ast` + `sqlite3` + `hashlib`), zero model
calls:

- **Stable identifiers** — `TYPE:<12-hex>` derived from file+qualname; a symbol
  keeps its ID while its identity is unchanged.
- **Incremental CodeIndex (DeltaIndexer)** — content-hash per file; reindex
  re-parses only changed files; removed files pruned. DB lives *outside* the
  scanned root (never mutates the project).
- **SQLite CodeGraph** — `files / symbols / edges` tables, relations
  `DEFINES, CALLS, IMPORTS, TESTED_BY`.
- **Hybrid Retriever** — `exact -> graph -> lexical (FTS5, bm25, AND→OR
  fallback)`, deterministic ordering, degrades gracefully when FTS5 is absent.
- **ContextCompiler** — target + callers + callees + tests as compact briefs;
  `verified=False` and `model_calls=0` always (Law 1: evidence, not
  verification).
- **Fail-closed** — unparseable files are stored with the reason and excluded
  from the graph, never dropped silently.
- **Scope discipline** — indexes only an explicitly supplied root; skip-list
  matches repo conventions (`.git`, `__pycache__`, `node_modules`, `build`,
  `dist`, `.lola-tools`, venvs).

Wiring: `lola.py --code-intel-smoke` (CI step) + `--code-intel DIR [--code-intel-db]`;
`lola_stack_verify` now reports the `code_intel` stage; toolchain-check
compiles the module; `tests/test_code_intel.py` (13 tests).

## Evidence

- Smoke: 14/14 deterministic checks (synthetic tree).
- Real repo: 282 files → 1,885 symbols / 4,645 edges, 0 failed, ~1.2 s.
- Suite: 614 passed (pytest, CI engine) vs 601 baseline.
- `--stack-verify` 24/24 modules + 3/3 stages.
- Perfs: `PRAGMA journal_mode=MEMORY, synchronous=OFF` on the rebuildable
  cache DB: 2.5 s → 4 ms DDL (safe: no user data in the index).

## Deferred (honest scope call)

- **ModelGateway / HF / LAN / local adapters** — need real endpoints + keys;
  design already reserved by `lola_cognition_ladder` + `llm_source_envelope`.
  Building an adapter that can't be pointed at anything is not evidence-based.
- **Cross-file call resolution** (imports → definitions across modules) —
  next iteration of the graph; current `CALLS` is intra-file, which is what
  ContextCompiler needs for v1.
- **FIM action, KV/prompt cache, runtime profiler, speculative decoding** —
  the thread itself sequences these after P0–P2 and after profiling proves
  the bottleneck ("LOLA should make the GGUF do less work" is the ordering
  principle: deterministic first).

## Invariants held

- Law 1: compiled context is structural evidence, `verified=False`.
- Law 2: default-deny scope — no root, no scan; nothing read outside it.
- Law 3: sovereign path — the whole layer runs with **zero** models.
- Law 4: failures surface (per-file errors in stats) and recheck is possible
  (reindex is idempotent; `graph_version` is a stable change fingerprint).
