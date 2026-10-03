# Interaction Gateway v1 — human/user control plane (design, frozen)

Date: 2026-10-03. Scope: the top slice of the Lola cognitive fabric —
everything between a human and the KERNEL_AI control plane. This spec
freezes the contract; transports beyond the three that already exist are
deliberately out of scope for v1.

## 1. The four laws

**Law 1 — User input is evidence, never verification.**
A human saying "it worked" enters as a `command`/`query` KIPEnvelope.
Only `VERIFY` backed by observation-grade evidence may set
`verified=True`. The epistemic fuse enforces this mechanically: a
verified claim whose cited evidence contains no observation-grade id is
CUT, regardless of who made the claim. (Philosophy already implicit in
`lola_sovereign_runtime.apply_observation` — "a model/user claim of
success is never sufficient by itself"; now explicit and testable.)

**Law 2 — Default-deny gate, three checks.**
Every normalized command passes, in order:
1. **actor known** — `actor_id` must exist in the actor table;
2. **trust class bound** — the envelope's `trust_class` must equal the
   actor's registered class (no trust escalation through the envelope);
3. **capability available + authority** — the requested capability must
   be in the source registry; if the command requires execution, the
   actor must hold the exact scope. Otherwise the command is denied.

Denial is not the end: the gateway returns an **escalation tuple**
(`session_id`, `transport`, reason) so the denial goes back to the human
on their own channel (Law 4). Execution authority in `RoutedCommand`
defaults to `False` and is granted only by an explicit scope match —
matching the repo-wide convention that every capability object defaults
to no authority.

**Law 3 — The sovereign path must stay reachable.**
The LLM source fabric (Tiny Local / Large Local / Remote Optional) is
expressed as a `CapabilityEnvelope` (reused from
`lola_sovereign_runtime`): local tiers are always local; the remote
tier only exists when `network_available=True`; with no tiers the
envelope is empty and the S0 sovereign path runs with zero models.
All LLM fabric output is grade-capped at **E3_INFERRED** — a model
statement can never self-certify as E0–E2.

**Law 4 — Failure returns to the human, not to a log.**
Escalation carries `session_id + transport` back through the gateway.
The gateway is the only component that holds session state (a table);
everything else in the slice is stateless. The loop closes at the
human — that is the difference between user control and user input.

## 2. Provenance contract (no new envelope)

KIPEnvelope v1.2 already carries `source` + `provenance`. The gateway
standardizes exactly five provenance keys; adapters must not add more:

```
provenance = {
  "actor_id":    str,              # who (stable id)
  "session_id":  str,              # gateway session table ref
  "transport":   str,              # cli | android | telegram | web | api | handoff
  "trust_class": str,              # LOCAL_DEVICE | TOKEN_BOUND | UNTRUSTED
  "authority":   str               # ADVISORY | EXECUTE:<scope>
}
```

`source` is `"transport:actor_id"`. `direct=True` only for
LOCAL_DEVICE (a direct human action on the device); TOKEN_BOUND and
UNTRUSTED are `direct=False`.

## 3. Components (this slice)

- `lola_interaction_gateway.py`
  - `TrustClass` enum; `TRANSPORTS` set (6, but v1 adapters: cli,
    android, handoff)
  - `ActorIdentity` (actor_id, trust_class, granted_scopes,
    `authority(scope)`)
  - `SessionTable` — deterministic session ids
    (sha256 of actor|transport|counter), `open_session`, `get_session`
  - `normalize_user_input(transport, raw, actor, *, session_id, kind,
    capability, requires_execution, execution_scope) -> KIPEnvelope`
  - `interaction_gate(envelope, actors, registry) -> RoutedCommand`
    (default-deny; `RoutedCommand` carries `path`,
    `execution_authority`, `denied_reasons`, `escalation`)
  - `llm_source_envelope(tiers, *, network_available)` +
    `grade_llm_output(source)` — Law 3
- `lola_epistemic_fuse.py`
  - `epistemic_fuse(*, verified, evidence_ids, observation_evidence_ids,
    contradictions) -> FuseVerdict` (PASS/CUT, Law 1)

## 4. Deliberately out of scope (v1)

- Telegram/Web/API adapters (contract is proven with cli/android/handoff;
  new transports are adapter exercises against this spec, not
  architecture changes)
- Any "smartness" in the gateway — it normalizes and gates only; if it
  starts interpreting commands it becomes a second kernel
- DURABLE vs EXPERIENCE: durable = where events are persisted
  (EventStore); experience = recall of *learned* knowledge via
  `retrieve_knowledge` (BLOCKED/QUARANTINED states; no silent fallback
  to superseded knowledge — existing test covers this)

## 5. Verification

- `tests/test_interaction_gateway.py` — RED→GREEN: normalization,
  rejection, all three gate checks, escalation shape, session
  determinism, S0 reachability, LLM grade cap, fuse laws
- Full unit suite + compile gate via CI (`Lola Bot Health`)
- No new dependencies (stdlib only)
