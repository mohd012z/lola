# Cognitive Entry — gateway → KIPEnvelope → loop integration — design (frozen)

Date: 2026-10-03. Source: Anam's architecture diagram (the connective
tissue between the Interaction Gateway #43 and the cognitive loop
#46-#49, which was the last unimplemented link in the chain).
Companion / capstone to the whole New LOLA build.

## Base
Built on `feat/loop-runner-recheck-v1` (PR #49) with
`feat/interaction-gateway-v1` (PR #43) merged in, so both halves are
present. Merge order: #42 → #43 → #44 → #45 → #46 → #47 → #48 → #49 → #50.

## Gap being closed
#43's gateway ends at a KIPEnvelope; #46-#49's loop starts from a raw
question. Nothing connected them, and the default-deny gate (Law 2) was
never actually exercised BEFORE cognition. The diagram's
`HUMAN → transports → GATEWAY → KIPEnvelope → KERNEL → loop → answer`
is now one call.

## Module R — `lola_cognitive_entry.py`
`cognitive_entry(transport, raw, actor, *, session_id, availability,
actors, capability="cognitive_query", verified_state=None,
inspectable=(), inventory=None, frozen_idea=None, external_hits=(),
prediction=None, observed=None, requires_execution=False,
execution_scope=None) -> EntryResult`

Pipeline (each stage frozen):
1. NORMALIZE — `normalize_user_input` → KIPEnvelope (5-key provenance).
2. GATE — `interaction_gate(envelope, actors, availability)`.
   - DENIED → return `EntryResult(status="DENIED", gate=routed,
     report=None, ...)`; cognition is NOT run (Law 2, default-deny
     before any thinking). `escalation` carries (session_id, transport,
     reason) — the denial's way back to the human on their own channel
     (Law 4).
   - ALLOWED → continue.
3. RUN — `run_cognitive_loop({...input from envelope.payload + the loop
   kwargs})` → the report. The envelope's `payload["input"]` is the
   question.
4. FUSE (Law 1) — if `external_hits` were used, the epistemic fuse
   (`lola_epistemic_fuse.fuse`) grades the result; a user claim is never
   treated as verification. Carried as `entry.fuse` (verdict name or None
   when no external evidence is involved).

`EntryResult` (frozen): status (DENIED|ANSWERED|...), gate (RoutedCommand),
report (dict|None), fuse (str|None), escalation (tuple|None),
session_id, transport.

Deterministic; the runner constructs a default S0 availability
(`CapabilityEnvelope(local=(capability,), remote=(), network_available
=False)`) when `availability` is omitted, so the sovereign no-model path
(Law 3) stays reachable and only trust/actor/scope checks can deny.

## CLI
`lola.py --cognitive-entry FILE.json` — input JSON:
`{transport, raw, actor: {actor_id, trust_class, granted_scopes[]},
  session_id, capability?, verified_state?, inspectable?, inventory?,
  frozen_idea?, external_hits?, prediction?, observed?}`. Runs
`cognitive_entry`, prints the EntryResult JSON. Exit 0 (runner reports,
does not gate). `actors` is built from the single `actor` in the file;
`availability` defaults to S0.

## Non-goals
No real transports/network/LLM; no new state beyond the (caller-owned)
SessionTable; the gateway stays stateless. Multi-actor routing and
web/telegram adapters remain deferred (Slice 2 of the gateway spec).
