# Delta-observe wiring + stack re-verification — design (frozen)

Date: 2026-10-03. Fatah chose option A (post-merge wiring) after the 9-PR
stack. This PR prepares the two post-merge deliverables so they land the
moment the #42→#51 chain merges: (1) wiring #42's DeltaMemory (the
prediction-error store) into the observe/recheck stage, and (2) a
post-merge re-verification that re-proves the whole stack on main.

## Base
Built on `feat/full-chain-smoke-doc-v1` (PR #51) with
`feat/gigachat-methods-v1` (PR #42) merged in, so both the delta store
and the full chain are present. Merge order:
#42 → ... → #51 → #52.

## Module S — `lola_delta_observe.py`
`PredictionErrorStore` — #42's `DeltaMemory(dim=1)` as the prediction-
error substrate for the observe stage:
- `prediction` (property) = the store's current recall (its forecast);
  0.0 for a fresh store.
- `observe(observed, *, a=0.0, b=4.0) -> dict` — one recurrence step:
  key/readout = the "this quantity" basis vector, value = `observed`.
  The delta rule stores `(value - read) * beta` — the conservative
  prediction-error write. Returns `prediction_error` (observed -
  predicted, the TRUE signed error), `stored_correction` (the beta-
  scaled delta actually written), `predicted`, `converged` (the store's
  updated forecast), `decay`, `beta`, `step`.
- `snapshot()` / `from_snapshot()` — the replayable audit trail (the
  StepRecord-equivalent state).
`run_recheck(store, observed_values) -> dict` — drives a sequence of
observations through the store; returns per-cycle records, the final
`converged_prediction`, `total_abs_error`, and the snapshot.

The delta rule's property — overwrite corrects, does not duplicate —
is exactly "store the prediction error, and let the forecast converge."

## Loop integration (additive)
`run_cognitive_loop(input)` — when `input` carries `observed_sequence`
(a list of numbers), it builds a `PredictionErrorStore`, runs
`run_recheck` over it, and attaches a `delta_store` section
{cycles, converged_prediction, total_abs_error} to the output. Absent →
no `delta_store` (all existing behavior unchanged). Exercised through
the existing `--cognitive-loop FILE.json` flag (no new flag).

## Module T — `lola_stack_verify.py`
`verify_merged_stack() -> dict` — the post-merge re-verification.
Imports every New LOLA module (the 9-PR set), runs the full-chain smoke
(#51), and runs a delta-observe cycle. Returns per-module import status
+ each stage's ok flag + overall `passed`. Runnable both on the stack
branch and, post-merge, on main — it is the single "the chain holds
together" re-check. `lola.py --stack-verify` prints it (exit 0/1).

## Non-goals
No new transports/LLM/network. No modification of #42's DeltaMemory
(used as-is). No change to the stateless recheck path.
