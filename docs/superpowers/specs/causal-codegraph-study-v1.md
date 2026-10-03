# Causal Delta × CodeGraph — study record and implementation (PR #57)

Date: 2026-10-03
Study source: shared thread `6ac0e84e-77fc-83ec-90d6-757d01c5e08d`
continuation, section **"5. Causal Delta × CodeGraph"** of its live-repo
recheck — explicitly named *"one of the strongest crossfunctions"*.

## What the thread prescribes

> Causal Delta immediately focuses on: `SSE decoder → Flow.emit`
> (the FIRST divergence) — "The GGUF doesn't need to search the entire
> project."

and its deterministic repair-rule example:

```
MISSING_MODULE_DEPENDENCY
    target   = app
    required = core
    evidence = symbol resolution
```

Plus the FAST-CODE property: *"Who calls ModelGateway.route?"* is answered
by IdentifierEngine + CodeGraph reverse edge, **GGUF calls: 0**.

## Cross-check vs main (465114c)

| Piece | Where |
|---|---|
| `causal_delta(task_id, expected)` — first-divergence primitive ({index, key, expected, actual}) | `lola_cognitive_fabric.py` (merged) |
| Stable symbol IDs, DEFINES/IMPORTS/CALLS/TESTED_BY edges, incremental index | `lola_code_intel.py` (PR #55, merged) |
| The CROSSFUNCTION (chain tracing + repair rules over the graph) | ❌ absent — built here |

## What this PR implements (`lola_causal_codegraph.py`, stdlib-only, zero model calls)

- `CausalCodeGraph(idx)` composing the two existing modules:
  - `_resolve(name)` — qualname → name → module-stem resolution with a
    **deterministic tie-break** (lexicographically smallest rel_path).
  - `trace_chain(chain, observed)` — per-step resolution + the
    **first divergence** in exactly the fabric's causal_delta output shape;
    `unresolved_tail` (steps after the divergence not in the graph);
    `graph_version` as the evidence scope.
  - **Sober failure:** unobserved = `?` (UNKNOWN, not a failure);
    not-in-graph = unknown, never invented as a failure.
  - Repair rules at the divergence, each a **hypothesis** (`verified=False`,
    Law 1): `UNRESOLVED_SYMBOL`, `MISSING_IMPORT` (evidence = the upstream
    file's actual import statements, read via AST under the index's
    root), `SAME_FILE_DEFINITION`, `UNPARSEABLE_FILE`,
    `CHECK_MISMATCH` fallback.
  - `callers(name)` / `who_calls(name)` — the FAST-CODE reverse lookup
    (incoming CALLS edges queried via `dst=?`; `symbol_neighbors` only
    returns outgoing edges — documented in-code), `model_calls: 0`.

Wiring (repo conventions): `lola.py --causal-graph-smoke`;
`lola_stack_verify._MODULES` (26 modules) + `causal_graph` stage;
`toolchain-check.yml` paths (push+PR) + compile list + "Causal Graph smoke
test" CI step; `tests/test_causal_codegraph.py` (19 tests).

## Evidence

- `pytest tests/test_causal_codegraph.py` — 19 passed (0.19 s).
- `--causal-graph-smoke` — 12/12 checks.
- Real-repo proof: indexed lola itself (286 files, 1990 symbols, 4854
  edges, 0 failed, ~0.9 s); traced a real in-graph chain
  (`verify_merged_stack` → `_candidate_ok`) — no divergence verified=True
  with graph-version scope; forced divergence → structural hypothesis
  (verified=False).

## Known limitation (honest)

Cross-file CALLS resolution is single-file in v1 (inherited from
`lola_code_intel`): a call to a symbol defined in another module has no
CALLS edge, so `who_calls` is exact only for same-file callers until
cross-file resolution lands. The repair rules are unaffected (they use
imports + file/parse state, not CALLS edges).
